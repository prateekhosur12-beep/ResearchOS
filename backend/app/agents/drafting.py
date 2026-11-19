"""Agent 3 — Drafting and Writing Agent.

Section-level generation so any section can be regenerated independently. The
bibliography is fixed before writing: the model may only cite keys that exist.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select

from app.agents.common import author_names
from app.db.base import SessionLocal
from app.db.models import Draft, Paper
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.skills.citation_format import CitationFormatInput, CitationFormatSkill
from app.skills.manuscript_section import SECTION_NAMES, ManuscriptSectionSkill

log = get_logger("agents.drafting")

DEFAULT_SECTIONS = [
    "abstract",
    "introduction",
    "related_work",
    "problem_statement",
    "objectives",
    "methodology",
    "proposed_experiments",
    "limitations",
    "conclusion",
]

SECTION_TITLES = {
    "abstract": "Abstract",
    "introduction": "1. Introduction",
    "related_work": "2. Related Work",
    "problem_statement": "3. Problem Statement",
    "objectives": "4. Research Objectives",
    "methodology": "5. Proposed Methodology",
    "proposed_experiments": "6. Proposed Experiments and Evaluation",
    "limitations": "7. Limitations",
    "conclusion": "8. Conclusion",
}


def _short_clause(text: str, limit: int) -> str:
    """First clause of a generated sentence, without quotes, capped at ``limit``."""
    text = " ".join((text or "").replace("\u201c", "").replace("\u201d", "").split())
    text = text.strip(' "\'')
    for sep in (" \u2014 ", " \u2013 ", " \u2014", "; ", ": ", ". "):
        if sep in text:
            head = text.split(sep)[0].strip()
            if len(head.split()) >= 3:
                text = head
                break
    if len(text) > limit:
        cut = text[:limit]
        if " " in cut:
            cut = cut[: cut.rindex(" ")]
        text = cut.rstrip(",;:-")
    return text


class DraftingAgent:
    name = "DraftingAgent"

    def __init__(self, runtime: AgentRuntime, tools) -> None:
        self.runtime = runtime
        self.tools = tools
        self.section_skill = ManuscriptSectionSkill()
        self.citation_skill = CitationFormatSkill()

    async def build_bibliography(
        self, papers: list[dict[str, Any]], limit: int = 12, style: str = "IEEE"
    ) -> list[dict[str, Any]]:
        chosen = papers[:limit]
        entries = [
            {
                "key": f"P{i + 1}",
                "paper_id": p["id"],
                "title": p["title"],
                "authors": p.get("authors") or [],
                "year": p.get("year"),
                "venue": p.get("venue"),
                "doi": p.get("doi"),
                "url": p.get("url"),
            }
            for i, p in enumerate(chosen)
        ]
        formatted = await self.citation_skill.run(
            CitationFormatInput(style=style, entries=entries).model_dump()
        )
        rendered = {r["key"]: r["text"] for r in formatted.data.get("formatted", [])}
        for e in entries:
            e["rendered"] = rendered.get(e["key"], "")
            e["rendered_in"] = style
        return entries

    async def run(
        self,
        *,
        project_id: str,
        topic: str,
        papers: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        idea: dict[str, Any] | None,
        domain: str = "computer_science",
        style: str = "IEEE",
        sections: list[str] | None = None,
        feedback: str | None = None,
        version_note: str | None = None,
    ) -> dict[str, Any]:
        if not papers:
            return {
                "ok": False,
                "error": "no papers available — refusing to draft unsupported prose",
                "sections": [],
            }

        await self.runtime.progress("drafting", "Preparing bibliography and drafting sections", agent=self.name)
        bibliography = await self.build_bibliography(papers, limit=12, style=style)
        section_list = [s for s in (sections or DEFAULT_SECTIONS) if s in SECTION_NAMES]

        sources = [
            {
                "paper_id": e["paper_id"],
                "key": e["key"],
                "title": e["title"],
                "abstract": next(
                    (p.get("abstract") for p in papers if p["id"] == e["paper_id"]), None
                ),
                "year": e["year"],
                "venue": e["venue"],
                "doi": e["doi"],
            }
            for e in bibliography
        ]

        produced: dict[str, Any] = {}
        warnings: list[str] = []
        generators: set[str] = set()
        for name in section_list:
            res = await self.section_skill.run(
                {
                    "section": name,
                    "topic": topic,
                    "sources": sources,
                    "gaps": gaps,
                    "idea": idea,
                    "domain": domain,
                    "word_target": 180 if name == "abstract" else 350,
                    "feedback": feedback,
                }
            )
            produced[name] = {
                "name": name,
                "markdown": res.data.get("markdown", ""),
                "citations": res.data.get("citations", []),
                "word_count": res.data.get("word_count", 0),
                "basis": res.data.get("basis", ""),
                "generated_by": res.generated_by,
            }
            generators.add(res.generated_by)
            warnings.extend(res.warnings)
            await self.runtime.emit(
                "section_drafted",
                stage="drafting",
                section=name,
                words=produced[name]["word_count"],
                generated_by=res.generated_by,
            )

        title = self._title(topic, gaps, idea)
        markdown = self._assemble(title, produced, bibliography, topic, version_note)

        draft = await self._persist(
            project_id=project_id,
            sections=produced,
            markdown=markdown,
            bibliography=bibliography,
            generated_by="+".join(sorted(generators)),
            title=title,
            style=style,
        )
        await self.runtime.emit(
            "draft_ready",
            stage="drafting",
            draft_id=draft["id"],
            version=draft["version"],
            words=sum(s["word_count"] for s in produced.values()),
            generated_by=draft["generated_by"],
        )
        return {
            "ok": True,
            "draft": draft,
            "bibliography": bibliography,
            "warnings": sorted(set(warnings)),
            "sections": list(produced),
        }

    # ------------------------------------------------------------------ helpers
    def _title(self, topic: str, gaps: list[dict[str, Any]], idea: dict[str, Any] | None) -> str:
        """A readable manuscript title.

        Gap and idea titles are generated sentences (often containing a quoted
        fragment from a paper). Dropping one into a manuscript title verbatim
        produces nonsense, so only a short leading clause is borrowed.
        """
        clean_topic = " ".join((topic or "").split()).rstrip(".")
        clause = ""
        if idea and idea.get("title"):
            candidate = str(idea["title"]).strip()
            # Idea titles are built as "Addressing <gap title>"; the interesting part
            # is the gap's own clause, not the wrapper word.
            if candidate.lower().startswith("addressing "):
                candidate = candidate[11:]
            if ":" in candidate:
                candidate = candidate.split(":", 1)[1]
            clause = _short_clause(candidate, 90)
        if not clause and gaps:
            gap_title = str(gaps[0].get("title", ""))
            if ":" in gap_title:
                gap_title = gap_title.split(":", 1)[1]
            clause = _short_clause(gap_title, 90)
        # Always keep the topic in the title: it is the only part the scholar is
        # guaranteed to recognise. The borrowed clause only adds the angle.
        if clause and clean_topic and clause.lower() not in clean_topic.lower():
            # lower-case the first letter for a subtitle, but never mangle an acronym
            head = clause if clause[:2].isupper() else clause[0].lower() + clause[1:]
            return f"{clean_topic}: {head}"
        if clean_topic:
            return f"A Reproducible Investigation of {clean_topic}"
        return "A Reproducible Investigation"

    def _assemble(
        self,
        title: str,
        sections: dict[str, Any],
        bibliography: list[dict[str, Any]],
        topic: str,
        version_note: str | None,
    ) -> str:
        lines = [
            f"# {title}",
            "",
            f"> **Draft generated by the Agentic AI Research Assistant** · "
            f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')} · "
            f"topic: *{topic}*",
            ">",
            "> This is a literature-grounded **proposal draft**. No experiments were executed and no "
            "empirical results are claimed. Every citation refers to a record retrieved by this "
            "project; unverified fields are marked in the citation audit.",
        ]
        if version_note:
            lines += ["", f"> {version_note}"]
        for name, sec in sections.items():
            if name == "abstract":
                lines += ["", "## Abstract", "", sec["markdown"]]
            else:
                lines += ["", f"## {SECTION_TITLES.get(name, name.title())}", "", sec["markdown"]]
        lines += ["", "## References", ""]
        for e in bibliography:
            lines.append(f"[{e['key']}] {e.get('rendered') or e['title']}")
        lines += [
            "",
            "---",
            "*Provenance: every reference above was retrieved from OpenAlex, Crossref or arXiv by this "
            "project and is stored with its retrieval timestamp in the project database.*",
        ]
        return "\n".join(lines)

    async def _persist(
        self,
        *,
        project_id: str,
        sections: dict[str, Any],
        markdown: str,
        bibliography: list[dict[str, Any]],
        generated_by: str,
        title: str,
        style: str,
    ) -> dict[str, Any]:
        async with SessionLocal() as session:
            current = (
                await session.execute(
                    select(func.max(Draft.version)).where(Draft.project_id == project_id)
                )
            ).scalar_one()
            version = int(current or 0) + 1
            draft = Draft(
                project_id=project_id,
                run_id=self.runtime.run_id,
                version=version,
                sections_json={
                    "title": title,
                    "style": style,
                    "sections": sections,
                    "bibliography": bibliography,
                },
                markdown=markdown,
                status="draft",
                generated_by=generated_by,
            )
            session.add(draft)
            await session.commit()
            return {
                "id": draft.id,
                "version": version,
                "status": draft.status,
                "generated_by": generated_by,
                "markdown": markdown,
                "sections": sections,
                "bibliography": bibliography,
                "title": title,
                "style": style,
            }

    async def latest(self, project_id: str) -> dict[str, Any] | None:
        async with SessionLocal() as session:
            draft = (
                await session.execute(
                    select(Draft)
                    .where(Draft.project_id == project_id)
                    .order_by(Draft.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if draft is None:
            return None
        return {
            "id": draft.id,
            "version": draft.version,
            "status": draft.status,
            "markdown": draft.markdown,
            "sections": (draft.sections_json or {}).get("sections", {}),
            "bibliography": (draft.sections_json or {}).get("bibliography", []),
            "generated_by": draft.generated_by,
            "updated_at": draft.updated_at.isoformat(),
        }

    async def paper_hint(self, papers: list[dict[str, Any]]) -> str:
        return "; ".join(f"{p['title'][:50]} ({p.get('year')})" for p in papers[:3])
