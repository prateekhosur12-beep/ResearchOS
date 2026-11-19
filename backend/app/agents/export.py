"""Agent 7 — Export and Repository Agent.

Writes real files into a project-scoped directory with safe filenames. Publication
artefacts (manuscript, full report) are gated behind a human approval when
`REQUIRE_APPROVAL_BEFORE_EXPORT` is on — the gate is enforced here, server-side,
not in the UI.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.agents.common import safe_slug
from app.config import settings
from app.db.base import SessionLocal
from app.db.models import (
    Approval,
    CitationReport,
    Collaborator,
    Draft,
    ExportRecord,
    Paper,
    Project,
    RadarResult,
    ResearchGap,
    WorkflowRun,
)
from app.logging_conf import get_logger

log = get_logger("agents.export")

EXPORT_KINDS = {
    "papers_csv",
    "papers_md",
    "gaps_md",
    "manuscript_md",
    "manuscript_docx",
    "citations_md",
    "citations_csv",
    "radar_md",
    "full_report_md",
}

APPROVAL_REQUIRED = {"manuscript_md", "manuscript_docx", "full_report_md"}


class ExportError(RuntimeError):
    pass


class ApprovalRequired(ExportError):
    pass


class ExportAgent:
    name = "ExportAgent"

    async def export(
        self,
        *,
        project_id: str,
        kind: str,
        run_id: str | None = None,
        actor: str = "user",
        force: bool = False,
    ) -> dict[str, Any]:
        if kind not in EXPORT_KINDS:
            raise ExportError(f"unknown export kind '{kind}'. Available: {sorted(EXPORT_KINDS)}")

        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            if project is None:
                raise ExportError("project not found")
            papers = (
                await session.execute(
                    select(Paper)
                    .where(Paper.project_id == project_id)
                    .order_by(Paper.rank_score.desc())
                )
            ).scalars().all()
            gaps = (
                await session.execute(
                    select(ResearchGap).where(ResearchGap.project_id == project_id)
                )
            ).scalars().all()
            draft = (
                await session.execute(
                    select(Draft)
                    .where(Draft.project_id == project_id)
                    .order_by(Draft.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            citation = (
                await session.execute(
                    select(CitationReport)
                    .where(CitationReport.project_id == project_id)
                    .order_by(CitationReport.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            radar = (
                await session.execute(
                    select(RadarResult).where(RadarResult.project_id == project_id)
                )
            ).scalars().all()
            collabs = (
                await session.execute(
                    select(Collaborator).where(Collaborator.project_id == project_id)
                )
            ).scalars().all()
            approval = (
                await session.execute(
                    select(Approval)
                    .where(
                        Approval.project_id == project_id,
                        Approval.artifact_type == "draft",
                        Approval.status == "approved",
                    )
                    .order_by(Approval.decided_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            run = None
            if run_id:
                run = await session.get(WorkflowRun, run_id)

        if kind in APPROVAL_REQUIRED and settings.require_approval_before_export and not force:
            if approval is None:
                raise ApprovalRequired(
                    "This artefact requires human approval before export. Submit the draft for "
                    "approval and approve it first (POST /projects/{id}/approvals)."
                )

        if not papers and kind in {"papers_csv", "papers_md", "full_report_md"}:
            raise ExportError("no papers stored for this project — nothing to export")

        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = f"{safe_slug(project.name)}_{kind}_{stamp}"
        out_dir = settings.export_path / project_id
        out_dir.mkdir(parents=True, exist_ok=True)

        if kind == "papers_csv":
            content = self._papers_csv(papers)
            path = out_dir / f"{base}.csv"
            path.write_text(content, encoding="utf-8")
        elif kind == "papers_md":
            path = out_dir / f"{base}.md"
            path.write_text(self._papers_md(project, papers), encoding="utf-8")
        elif kind == "gaps_md":
            path = out_dir / f"{base}.md"
            path.write_text(self._gaps_md(project, gaps, papers), encoding="utf-8")
        elif kind in {"manuscript_md", "manuscript_docx"}:
            if draft is None:
                raise ExportError("no draft exists for this project")
            if kind == "manuscript_md":
                path = out_dir / f"{base}.md"
                path.write_text(draft.markdown, encoding="utf-8")
            else:
                path = out_dir / f"{base}.docx"
                self._write_docx(path, draft.markdown)
        elif kind in {"citations_md", "citations_csv"}:
            if citation is None:
                raise ExportError("no citation audit exists for this project")
            if kind == "citations_md":
                path = out_dir / f"{base}.md"
                path.write_text(self._citations_md(project, citation.report_json), encoding="utf-8")
            else:
                path = out_dir / f"{base}.csv"
                path.write_text(self._citations_csv(citation.report_json), encoding="utf-8")
        elif kind == "radar_md":
            path = out_dir / f"{base}.md"
            path.write_text(self._radar_md(project, radar, collabs), encoding="utf-8")
        else:  # full_report_md
            path = out_dir / f"{base}.md"
            path.write_text(
                self._full_report(project, papers, gaps, draft, citation, radar, collabs, run),
                encoding="utf-8",
            )

        size = path.stat().st_size
        async with SessionLocal() as session:
            rec = ExportRecord(
                project_id=project_id,
                run_id=run_id,
                kind=kind,
                filename=path.name,
                rel_path=str(path.relative_to(settings.export_path)),
                size_bytes=size,
                approved_by=(approval.actor if approval else None),
            )
            session.add(rec)
            await session.commit()
            export_id = rec.id

        log.info("export written kind=%s path=%s bytes=%s", kind, path.name, size)
        return {
            "id": export_id,
            "kind": kind,
            "filename": path.name,
            "rel_path": str(path.relative_to(settings.export_path)),
            "size_bytes": size,
            "download_url": f"/api/exports/{project_id}/{path.name}",
            "approval": "approved" if approval else ("not_required" if kind not in APPROVAL_REQUIRED else "forced"),
        }

    # ------------------------------------------------------------- renderers
    def _papers_csv(self, papers: list[Paper]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["title", "authors", "year", "venue", "doi", "arxiv_id", "sources", "cited_by", "url", "retrieved_at"]
        )
        for p in papers:
            writer.writerow(
                [
                    p.title,
                    "; ".join(a.get("name", "") for a in (p.authors_json or [])),
                    p.year or "",
                    p.venue or "",
                    p.doi or "",
                    p.arxiv_id or "",
                    ",".join(p.sources_json or []),
                    p.cited_by if p.cited_by is not None else "",
                    p.url or "",
                    p.retrieved_at.isoformat() if p.retrieved_at else "",
                ]
            )
        return buf.getvalue()

    def _papers_md(self, project: Project, papers: list[Paper]) -> str:
        lines = [
            f"# Literature list — {project.name}",
            "",
            f"**Topic:** {project.topic}  ",
            f"**Records:** {len(papers)}  ",
            f"**Exported:** {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}  ",
            f"**Provenance:** retrieved from OpenAlex / Crossref / arXiv by project `{project.id}`",
            "",
            "| # | Title | Year | Venue | Identifier | Sources | Rank |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, p in enumerate(papers, 1):
            ident = p.doi or (f"arXiv:{p.arxiv_id}" if p.arxiv_id else p.url or "—")
            lines.append(
                f"| {i} | {p.title[:110]} | {p.year or 'n.d.'} | {(p.venue or '—')[:40]} | "
                f"{ident} | {', '.join(p.sources_json or [])} | {p.rank_score:.3f} |"
            )
        return "\n".join(lines)

    def _gaps_md(self, project: Project, gaps: list[ResearchGap], papers: list[Paper]) -> str:
        by_id = {p.id: p for p in papers}
        lines = [
            f"# Research gap report — {project.name}",
            "",
            f"**Topic:** {project.topic}",
            f"**Gaps:** {len(gaps)} "
            f"({sum(1 for g in gaps if g.kind == 'evidence_backed')} evidence-backed, "
            f"{sum(1 for g in gaps if g.kind == 'hypothesis')} hypothesis)",
            "",
            "> Evidence-backed gaps quote limitations the authors state. Hypothesis gaps are "
            "cross-paper patterns proposed by the assistant and must be validated by a human.",
            "",
        ]
        for i, g in enumerate(gaps, 1):
            lines += [
                f"## G{i}. {g.title}",
                "",
                f"*Type:* **{g.kind}** · *confidence:* {g.confidence:.2f} · "
                f"*generated by:* `{g.generated_by}`",
                "",
                g.description,
                "",
            ]
            if g.rationale:
                lines += [f"**Why this is a gap:** {g.rationale}", ""]
            if g.evidence_quotes:
                lines.append("**Quoted evidence**")
                lines.append("")
                for q in g.evidence_quotes:
                    src = by_id.get(q.get("paper_id"))
                    title = src.title if src else q.get("paper_id")
                    lines.append(f"> “{q.get('quote', '')}”  \n> — *{title}*")
                    lines.append("")
            lines.append("**Supporting papers**")
            lines.append("")
            for pid in g.evidence_paper_ids:
                p = by_id.get(pid)
                if not p:
                    lines.append(f"- (paper id {pid} no longer in project)")
                    continue
                ident = p.doi or (f"arXiv:{p.arxiv_id}" if p.arxiv_id else p.url or "no id")
                lines.append(f"- {p.title} ({p.year or 'n.d.'}) — {ident}")
            if g.suggested_metrics:
                lines += ["", f"**Suggested metrics:** {', '.join(g.suggested_metrics)}"]
            lines.append("")
        return "\n".join(lines)

    def _citations_md(self, project: Project, report: dict[str, Any]) -> str:
        s = report.get("summary", {})
        lines = [
            f"# Citation audit — {project.name}",
            "",
            f"**Topic:** {project.topic}",
            f"**Draft version:** {report.get('draft_version')}",
            "",
            "| Check | Result |",
            "|---|---|",
            f"| References | {s.get('references', 0)} |",
            f"| In-text markers | {s.get('in_text_markers', 0)} |",
            f"| DOI resolved | {s.get('doi_verified', 0)} |",
            f"| DOI failed | {s.get('doi_failed', 0)} |",
            f"| DOI unavailable | {s.get('doi_unavailable', 0)} |",
            f"| Missing bibliography entries | {len(s.get('missing_bibliography_entries', []))} |",
            f"| Unused bibliography entries | {len(s.get('unused_bibliography_entries', []))} |",
            f"| Duplicate references | {len(s.get('duplicates', []))} |",
            "",
            f"> {report.get('statement', '')}",
            "",
            "## Per-reference results",
            "",
            "| Key | Title | DOI | Metadata check | Issues |",
            "|---|---|---|---|---|",
        ]
        for e in report.get("entries", []):
            lines.append(
                f"| {e['key']} | {e['title'][:60]} | {e.get('doi') or '—'} | "
                f"{e['metadata_check']} | {'; '.join(e.get('issues') or []) or 'none'} |"
            )
        return "\n".join(lines)

    def _citations_csv(self, report: dict[str, Any]) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["key", "title", "doi", "metadata_check", "cited_in_text", "title_similarity", "issues"])
        for e in report.get("entries", []):
            w.writerow(
                [
                    e["key"],
                    e["title"],
                    e.get("doi") or "",
                    e["metadata_check"],
                    e.get("cited_in_text", ""),
                    e.get("title_similarity", ""),
                    "; ".join(e.get("issues") or []),
                ]
            )
        return buf.getvalue()

    def _radar_md(self, project: Project, radar: list[RadarResult], collabs: list[Collaborator]) -> str:
        lines = [
            f"# Venue, funding and collaboration radar — {project.name}",
            "",
            f"**Topic:** {project.topic}",
            "",
            "## Venues",
            "",
            "| Venue (as seen in literature) | Verification | Publisher | ISSN | Papers | Note |",
            "|---|---|---|---|---|---|",
        ]
        for r in radar:
            if r.kind != "journal":
                continue
            p = r.payload_json or {}
            lines.append(
                f"| {p.get('venue_in_literature', r.name)} | {r.verification} | "
                f"{p.get('publisher') or '—'} | {p.get('issn') or '—'} | {p.get('papers_in_corpus', 0)} | "
                f"{p.get('note', '')[:100]} |"
            )
        lines += ["", "## Funders active in this literature", ""]
        funders = [r for r in radar if r.kind == "funding"]
        if funders:
            for r in funders:
                p = r.payload_json or {}
                awards = ", ".join(p.get("award_ids", [])[:3]) or "no award id recorded"
                lines.append(f"- **{r.name}** — {len(p.get('papers', []))} paper(s) in corpus; awards: {awards}")
        else:
            lines.append("_No funder metadata was available on the retrieved records._")
        lines += [
            "",
            "## Collaboration candidates",
            "",
            "| Name | Papers in corpus | Latest year | Institutions | Evidence |",
            "|---|---|---|---|---|",
        ]
        for c in collabs:
            insts = ", ".join((c.relevant_papers or [{}])[0].get("institutions", [])[:0]) if False else ""
            lines.append(
                f"| {c.name} | {c.works_count} | — | — | {c.evidence_note or ''} |"
            )
        lines += [
            "",
            "> Research similarity is not evidence of availability, willingness or funding. "
            "Contact details are never inferred.",
        ]
        return "\n".join(lines)

    def _full_report(
        self,
        project: Project,
        papers: list[Paper],
        gaps: list[ResearchGap],
        draft: Draft | None,
        citation: CitationReport | None,
        radar: list[RadarResult],
        collabs: list[Collaborator],
        run: WorkflowRun | None,
    ) -> str:
        parts = [
            f"# Complete research dossier — {project.name}",
            "",
            f"**Topic:** {project.topic}  ",
            f"**Project id:** `{project.id}`  ",
            f"**Domain:** {project.domain}  ",
            f"**Generated:** {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
            "",
            "## 1. Literature",
            "",
            self._papers_md(project, papers),
            "",
            "## 2. Research gaps",
            "",
            self._gaps_md(project, gaps, papers),
            "",
        ]
        if draft:
            parts += [
                f"## 3. Manuscript draft (v{draft.version}, {draft.status})",
                "",
                f"*Generated by:* `{draft.generated_by}`",
                "",
                draft.markdown,
                "",
            ]
        if citation:
            parts += ["## 4. Citation audit", "", self._citations_md(project, citation.report_json), ""]
        parts += ["## 5. Venues, funding and collaborators", "", self._radar_md(project, radar, collabs), ""]
        if run and (run.stats_json or {}).get("deep_research"):
            dr = run.stats_json["deep_research"]
            if dr.get("report_markdown"):
                parts += ["## 6. Deep research report", "", dr["report_markdown"], ""]
        parts += [
            "---",
            "*Every bibliographic record in this dossier was retrieved from a live scholarly API by "
            "this project. Model-generated text is labelled at the section level. Statements marked "
            "as hypothesis are proposals, not findings.*",
        ]
        return "\n".join(parts)

    def _write_docx(self, path: Path, markdown: str) -> None:
        from docx import Document
        from docx.shared import Pt

        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)
        in_table = False
        table_rows: list[list[str]] = []

        def flush_table() -> None:
            nonlocal in_table, table_rows
            if not table_rows:
                in_table = False
                return
            rows = [r for r in table_rows if not re.match(r"^\|[\s\-|:]+\|$", "|".join(r) + "|")]
            if rows:
                cols = max(len(r) for r in rows)
                table = doc.add_table(rows=0, cols=cols)
                table.style = "Light Grid Accent 1"
                for r in rows:
                    cells = table.add_row().cells
                    for i in range(cols):
                        cells[i].text = (r[i] if i < len(r) else "").strip()
            table_rows = []
            in_table = False

        for raw in markdown.splitlines():
            line = raw.rstrip()
            if line.startswith("|"):
                in_table = True
                cells = [c for c in line.strip().strip("|").split("|")]
                table_rows.append(cells)
                continue
            if in_table:
                flush_table()
            stripped = line.lstrip()
            if stripped.startswith("### "):
                doc.add_heading(stripped[4:].strip(), level=3)
            elif stripped.startswith("## "):
                doc.add_heading(stripped[3:].strip(), level=2)
            elif stripped.startswith("# "):
                doc.add_heading(stripped[2:].strip(), level=1)
            elif stripped.startswith("> "):
                p = doc.add_paragraph(stripped[2:])
                p.style = doc.styles["Intense Quote"]
            elif stripped.startswith(("- ", "* ")):
                doc.add_paragraph(stripped[2:], style="List Bullet")
            elif re.match(r"^\d+\.\s", stripped):
                doc.add_paragraph(re.sub(r"^\d+\.\s", "", stripped), style="List Number")
            elif not stripped:
                continue
            else:
                text = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
                text = re.sub(r"[*_](.+?)[*_]", r"\1", text)
                doc.add_paragraph(text)
        flush_table()
        doc.save(str(path))
