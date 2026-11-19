"""Workspace endpoints: literature, gaps, ideas, draft, citations, radar, retrieval."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agents.citation import CitationComplianceAgent
from app.api.deps import create_manual_run, get_project_or_404, iso
from app.db.base import SessionLocal
from app.db.models import (
    CitationReport,
    Collaborator,
    Draft,
    Paper,
    RadarResult,
    ResearchGap,
    ResearchIdea,
    WorkflowRun,
)
from app.runtime.runtime import AgentRuntime
from app.services.embeddings import semantic_search
from app.skills.manuscript_section import SECTION_NAMES, ManuscriptSectionSkill
from app.tools.runner import ToolRunner

router = APIRouter(prefix="/api/projects", tags=["workspace"])


# --------------------------------------------------------------------- papers
@router.get("/{project_id}/papers")
async def list_papers(
    project_id: str,
    q: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    source: str | None = None,
    sort: str = "rank",
    limit: int = 200,
) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        stmt = select(Paper).where(Paper.project_id == project_id)
        if year_from:
            stmt = stmt.where(Paper.year >= year_from)
        if year_to:
            stmt = stmt.where(Paper.year <= year_to)
        rows = (await session.execute(stmt)).scalars().all()

    if q:
        needle = q.lower()
        rows = [
            p
            for p in rows
            if needle in (p.title or "").lower()
            or needle in (p.abstract or "").lower()
            or needle in (p.doi or "").lower()
        ]
    if source:
        rows = [p for p in rows if source in (p.sources_json or [])]
    if sort == "year":
        rows.sort(key=lambda p: -(p.year or 0))
    elif sort == "citations":
        rows.sort(key=lambda p: -(p.cited_by or 0))
    else:
        rows.sort(key=lambda p: -p.rank_score)
    rows = rows[:limit]

    return {
        "count": len(rows),
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "doi": p.doi,
                "arxiv_id": p.arxiv_id,
                "authors": (p.authors_json or [])[:8],
                "year": p.year,
                "venue": p.venue,
                "abstract": p.abstract,
                "url": p.url,
                "pdf_url": p.pdf_url,
                "cited_by": p.cited_by,
                "type": p.type,
                "sources": p.sources_json or [],
                "retrieved_at": iso(p.retrieved_at),
                "rank_score": p.rank_score,
                "rank_explain": p.rank_explain_json or {},
                "is_selected": p.is_selected,
                "metadata_warnings": (
                    ["abstract not available"] if not p.abstract else []
                ),
            }
            for p in rows
        ],
    }


class PaperPatch(BaseModel):
    is_selected: bool | None = None
    user_note: str | None = None


@router.patch("/{project_id}/papers/{paper_id}")
async def patch_paper(project_id: str, paper_id: str, payload: PaperPatch) -> dict[str, Any]:
    async with SessionLocal() as session:
        paper = await session.get(Paper, paper_id)
        if paper is None or paper.project_id != project_id:
            raise HTTPException(status_code=404, detail="paper not found in this project")
        if payload.is_selected is not None:
            paper.is_selected = payload.is_selected
        if payload.user_note is not None:
            paper.user_note = payload.user_note
        await session.commit()
    return {"ok": True, "paper_id": paper_id}


# ---------------------------------------------------------------------- gaps
@router.get("/{project_id}/gaps")
async def list_gaps(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        gaps = (
            await session.execute(
                select(ResearchGap)
                .where(ResearchGap.project_id == project_id)
                .order_by(ResearchGap.confidence.desc())
            )
        ).scalars().all()
        papers = (
            await session.execute(select(Paper).where(Paper.project_id == project_id))
        ).scalars().all()
    by_id = {p.id: p for p in papers}
    return {
        "count": len(gaps),
        "gaps": [
            {
                "id": g.id,
                "title": g.title,
                "description": g.description,
                "rationale": g.rationale,
                "kind": g.kind,
                "confidence": g.confidence,
                "feasibility": g.feasibility,
                "suggested_metrics": g.suggested_metrics or [],
                "generated_by": g.generated_by,
                "evidence": [
                    {
                        "paper_id": pid,
                        "title": by_id[pid].title if pid in by_id else None,
                        "year": by_id[pid].year if pid in by_id else None,
                        "doi": by_id[pid].doi if pid in by_id else None,
                        "url": by_id[pid].url if pid in by_id else None,
                    }
                    for pid in (g.evidence_paper_ids or [])
                ],
                "evidence_quotes": g.evidence_quotes or [],
            }
            for g in gaps
        ],
    }


@router.get("/{project_id}/ideas")
async def list_ideas(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        ideas = (
            await session.execute(
                select(ResearchIdea).where(ResearchIdea.project_id == project_id)
            )
        ).scalars().all()
    return {
        "count": len(ideas),
        "label": "PROPOSED — not conducted research",
        "ideas": [
            {
                "id": i.id,
                "title": i.title,
                "research_questions": i.research_questions or [],
                "objectives": i.objectives or [],
                "proposed_methodology": i.proposed_methodology,
                "suggested_datasets": i.suggested_datasets or [],
                "metrics": i.metrics or [],
                "challenges": i.challenges or [],
                "feasibility": i.feasibility,
                "generated_by": i.generated_by,
            }
            for i in ideas
        ],
    }


# --------------------------------------------------------------------- draft
def _draft_payload(d: Draft) -> dict[str, Any]:
    sections = (d.sections_json or {}).get("sections", {})
    return {
        "id": d.id,
        "version": d.version,
        "status": d.status,
        "markdown": d.markdown,
        "title": (d.sections_json or {}).get("title"),
        "style": (d.sections_json or {}).get("style"),
        "generated_by": d.generated_by,
        "updated_at": iso(d.updated_at),
        "bibliography": (d.sections_json or {}).get("bibliography", []),
        "sections": [
            {
                "name": name,
                "markdown": s.get("markdown", ""),
                "word_count": s.get("word_count", 0),
                "generated_by": s.get("generated_by", ""),
                "basis": s.get("basis", ""),
                "citations": s.get("citations", []),
            }
            for name, s in sections.items()
        ],
    }


@router.get("/{project_id}/draft")
async def get_draft(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        draft = (
            await session.execute(
                select(Draft)
                .where(Draft.project_id == project_id)
                .order_by(Draft.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if draft is None:
            return {"exists": False, "draft": None}
        versions = (
            await session.execute(
                select(Draft.version, Draft.status, Draft.created_at, Draft.generated_by)
                .where(Draft.project_id == project_id)
                .order_by(Draft.version.desc())
            )
        ).all()
        return {
            "exists": True,
            "draft": _draft_payload(draft),
            "versions": [
                {"version": v, "status": s, "created_at": iso(c), "generated_by": g}
                for v, s, c, g in versions
            ],
        }


class SectionPatch(BaseModel):
    section: str
    markdown: str


@router.patch("/{project_id}/draft/section")
async def edit_section(project_id: str, payload: SectionPatch) -> dict[str, Any]:
    """User edit of one section — creates a new version, preserving history."""
    if payload.section not in SECTION_NAMES:
        raise HTTPException(status_code=400, detail=f"unknown section; expected one of {SECTION_NAMES}")
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        latest = (
            await session.execute(
                select(Draft)
                .where(Draft.project_id == project_id)
                .order_by(Draft.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=404, detail="no draft to edit")
        data = dict(latest.sections_json or {})
        sections = dict(data.get("sections", {}))
        sec = dict(sections.get(payload.section, {}))
        sec.update(
            {
                "name": payload.section,
                "markdown": payload.markdown,
                "word_count": len(payload.markdown.split()),
                "generated_by": "human-edit",
                "basis": "edited by the user",
            }
        )
        sections[payload.section] = sec
        data["sections"] = sections
        new_draft = Draft(
            project_id=project_id,
            run_id=latest.run_id,
            version=latest.version + 1,
            sections_json=data,
            markdown=_rebuild_markdown(data),
            status="draft",
            generated_by="human-edit",
        )
        session.add(new_draft)
        await session.commit()
        await session.refresh(new_draft)
        return {"ok": True, "draft": _draft_payload(new_draft)}


class RegenerateSection(BaseModel):
    section: str
    feedback: str | None = None


@router.post("/{project_id}/draft/regenerate")
async def regenerate_section(project_id: str, payload: RegenerateSection) -> dict[str, Any]:
    """Regenerate exactly one section, keeping the rest of the draft intact."""
    if payload.section not in SECTION_NAMES:
        raise HTTPException(status_code=400, detail=f"unknown section; expected one of {SECTION_NAMES}")
    run_id = await create_manual_run(project_id, f"regenerate:{payload.section}")
    runtime = AgentRuntime(run_id=run_id, project_id=project_id)
    tool_runner = ToolRunner(project_id=project_id, run_id=run_id)
    try:
        async with SessionLocal() as session:
            project = await get_project_or_404(session, project_id)
            latest = (
                await session.execute(
                    select(Draft)
                    .where(Draft.project_id == project_id)
                    .order_by(Draft.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if latest is None:
                raise HTTPException(status_code=404, detail="no draft exists yet")
            gaps = (
                await session.execute(
                    select(ResearchGap).where(ResearchGap.project_id == project_id)
                )
            ).scalars().all()
            papers = (
                await session.execute(
                    select(Paper)
                    .where(Paper.project_id == project_id)
                    .order_by(Paper.rank_score.desc())
                    .limit(12)
                )
            ).scalars().all()

        data = dict(latest.sections_json or {})
        bibliography = data.get("bibliography", [])
        idea = await _latest_idea(project_id)
        skill = ManuscriptSectionSkill()
        sources = [
            {
                "paper_id": e["paper_id"],
                "key": e["key"],
                "title": e["title"],
                "abstract": next((p.abstract for p in papers if p.id == e["paper_id"]), None),
                "year": e.get("year"),
                "venue": e.get("venue"),
                "doi": e.get("doi"),
            }
            for e in bibliography
        ]
        res = await runtime.step(
            "DraftingAgent",
            f"regenerate:{payload.section}",
            lambda: skill.run(
                {
                    "section": payload.section,
                    "topic": project.topic,
                    "sources": sources,
                    "gaps": [
                        {"title": g.title, "description": g.description, "kind": g.kind,
                         "evidence_paper_ids": g.evidence_paper_ids or []}
                        for g in gaps
                    ],
                    "idea": idea,
                    "domain": project.domain,
                    "feedback": payload.feedback,
                }
            ),
        )
        if not res.ok:
            raise HTTPException(status_code=502, detail=res.error)

        skill_result = res.value
        sections = dict(data.get("sections", {}))
        sections[payload.section] = {
            "name": payload.section,
            "markdown": skill_result.data.get("markdown", ""),
            "word_count": skill_result.data.get("word_count", 0),
            "generated_by": skill_result.generated_by,
            "basis": skill_result.data.get("basis", ""),
            "citations": skill_result.data.get("citations", []),
        }
        data["sections"] = sections
        async with SessionLocal() as session:
            new_draft = Draft(
                project_id=project_id,
                run_id=run_id,
                version=latest.version + 1,
                sections_json=data,
                markdown=_rebuild_markdown(data),
                status="draft",
                generated_by=skill_result.generated_by,
            )
            session.add(new_draft)
            await session.commit()
            await session.refresh(new_draft)
            payload_out = _draft_payload(new_draft)
        return {
            "ok": True,
            "draft": payload_out,
            "generated_by": skill_result.generated_by,
            "warnings": skill_result.warnings,
        }
    finally:
        await tool_runner.aclose()


def _rebuild_markdown(data: dict[str, Any]) -> str:
    from app.agents.drafting import SECTION_TITLES

    lines = [f"# {data.get('title', 'Untitled draft')}", ""]
    bibliography = data.get("bibliography", [])
    for name, sec in (data.get("sections") or {}).items():
        if name == "abstract":
            lines += ["## Abstract", "", sec.get("markdown", "")]
        else:
            lines += ["", f"## {SECTION_TITLES.get(name, name.title())}", "", sec.get("markdown", "")]
    lines += ["", "## References", ""]
    for e in bibliography:
        lines.append(f"[{e['key']}] {e.get('rendered') or e.get('title', '')}")
    lines += ["", "---", "*Provenance: every reference was retrieved by this project from a live scholarly API.*"]
    return "\n".join(lines)


async def _latest_idea(project_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as session:
        idea = (
            await session.execute(
                select(ResearchIdea).where(ResearchIdea.project_id == project_id).limit(1)
            )
        ).scalar_one_or_none()
    if idea is None:
        return None
    return {
        "title": idea.title,
        "research_questions": idea.research_questions or [],
        "objectives": idea.objectives or [],
        "proposed_methodology": idea.proposed_methodology,
        "suggested_datasets": idea.suggested_datasets or [],
        "metrics": idea.metrics or [],
    }


# ----------------------------------------------------------------- citations
@router.get("/{project_id}/citations")
async def get_citations(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        row = (
            await session.execute(
                select(CitationReport)
                .where(CitationReport.project_id == project_id)
                .order_by(CitationReport.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if row is None:
        return {"exists": False, "report": None}
    return {"exists": True, "report": row.report_json, "created_at": iso(row.created_at)}


@router.post("/{project_id}/citations/audit")
async def reaudit_citations(project_id: str) -> dict[str, Any]:
    """Re-run the live DOI audit against the current draft (real network calls)."""
    run_id = await create_manual_run(project_id, "citation_audit")
    runtime = AgentRuntime(run_id=run_id, project_id=project_id)
    tools = ToolRunner(project_id=project_id, run_id=run_id)
    try:
        await tools.start()
        async with SessionLocal() as session:
            await get_project_or_404(session, project_id)
            draft = (
                await session.execute(
                    select(Draft)
                    .where(Draft.project_id == project_id)
                    .order_by(Draft.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if draft is None:
            raise HTTPException(status_code=404, detail="no draft to audit")
        agent = CitationComplianceAgent(runtime, tools)
        res = await agent.run(
            project_id=project_id,
            draft={"id": draft.id, "version": draft.version, "markdown": draft.markdown},
            bibliography=(draft.sections_json or {}).get("bibliography", []),
        )
        async with SessionLocal() as session:
            from app.db.models import WorkflowRun as WR

            run = await session.get(WR, run_id)
            if run:
                run.status = "completed"
                run.stage = "citation_audit"
                run.stats_json = {"summary": res["report"]["summary"]}
        return {"ok": True, "report": res["report"], "warnings": res["warnings"], "run_id": run_id}
    finally:
        await tools.aclose()


# -------------------------------------------------------------------- radar
@router.get("/{project_id}/radar")
async def get_radar(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        rows = (
            await session.execute(
                select(RadarResult)
                .where(RadarResult.project_id == project_id)
                .order_by(RadarResult.kind, RadarResult.name)
            )
        ).scalars().all()
        collabs = (
            await session.execute(
                select(Collaborator).where(Collaborator.project_id == project_id)
            )
        ).scalars().all()
    return {
        "journals": [
            {"name": r.name, **r.payload_json, "verification": r.verification, "source_url": r.source_url,
             "retrieved_at": iso(r.retrieved_at)}
            for r in rows
            if r.kind == "journal"
        ],
        "funding": [
            {"name": r.name, **r.payload_json, "verification": r.verification,
             "retrieved_at": iso(r.retrieved_at)}
            for r in rows
            if r.kind == "funding"
        ],
        "collaborators": [
            {
                "name": c.name,
                "author_key": c.author_key,
                "papers_in_corpus": c.works_count,
                "similarity": c.similarity,
                "evidence_note": c.evidence_note,
                "papers": c.relevant_papers or [],
                "source_url": c.source_url,
            }
            for c in collabs
        ],
        "disclaimers": {
            "venues": (
                "Verified = title/ISSN/publisher confirmed in the Crossref journal registry. "
                "Impact factor and acceptance rate are not available from these sources."
            ),
            "funding": (
                "Funders and award IDs are those recorded on real publications, plus OpenAlex funder "
                "entities. No deadlines, amounts or eligibility are claimed."
            ),
            "collaboration": (
                "Candidates are real authors of retrieved records. Similarity ≠ availability."
            ),
        },
    }


# ------------------------------------------------------------------ retrieval
class RetrievalQuery(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    limit: int = Field(default=8, ge=1, le=30)


@router.post("/{project_id}/retrieval/search")
async def retrieval_search(project_id: str, payload: RetrievalQuery) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        res = await semantic_search(session, project_id, payload.query, limit=payload.limit)
    return res


# -------------------------------------------------------------- deep research
@router.get("/{project_id}/deep-research")
async def get_deep_research(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        run = (
            await session.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == project_id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    dr = ((run.stats_json or {}).get("deep_research") if run else None) or {}
    return {"exists": bool(dr), "deep_research": dr, "run_id": run.id if run else None}
