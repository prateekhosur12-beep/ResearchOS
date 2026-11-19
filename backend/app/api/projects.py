"""Project CRUD. Every project is an isolation boundary for literature and artefacts."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, func, select

from app.api.deps import get_project_or_404, iso
from app.db.base import SessionLocal
from app.db.models import (
    CitationReport,
    Collaborator,
    Draft,
    Paper,
    PaperVector,
    Project,
    RadarResult,
    ResearchGap,
    ResearchIdea,
    WorkflowRun,
)
from app.schemas.models import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.query_planner import plan_queries
from app.services.stages import stages_from_stats
from app.services.workflow_service import workflow_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


async def _project_out(session, p: Project) -> ProjectOut:
    from app.services.workflow_service import workflow_service

    async def count(model) -> int:
        return (
            await session.execute(select(func.count(model.id)).where(model.project_id == p.id))
        ).scalar_one()

    latest = (
        await session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == p.id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return ProjectOut(
        id=p.id,
        name=p.name,
        topic=p.topic,
        domain=p.domain,
        status=p.status,
        created_at=iso(p.created_at) or "",
        updated_at=iso(p.updated_at) or "",
        research_instructions=p.research_instructions or "",
        research_questions=list(p.research_questions or []),
        paper_count=await count(Paper),
        run_count=await count(WorkflowRun),
        draft_count=await count(Draft),
        gap_count=await count(ResearchGap),
        idea_count=await count(ResearchIdea),
        last_run_status=latest.status if latest else None,
        active_run_id=latest.id if latest and workflow_service.is_active(latest.id) else None,
    )


@router.post("", response_model=ProjectOut)
async def create_project(payload: ProjectCreate) -> ProjectOut:
    from app.agents.domain import resolve_domain

    async with SessionLocal() as session:
        project = Project(
            name=payload.name or payload.topic[:120],
            topic=payload.topic,
            domain=resolve_domain(payload.domain, payload.topic),
            research_instructions=payload.research_instructions or None,
            research_questions=payload.research_questions or None,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return await _project_out(session, project)


@router.get("", response_model=list[ProjectOut])
async def list_projects() -> list[ProjectOut]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Project).order_by(Project.updated_at.desc()))
        ).scalars().all()
        return [await _project_out(session, p) for p in rows]


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        project = await get_project_or_404(session, project_id)
        out = await _project_out(session, project)
        runs = (
            await session.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == project_id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        # Fast preview (no model call) so the detail endpoint stays snappy; the
        # /queries endpoint refreshes with the LLM when asked.
        plan_preview = await plan_queries(
            topic=project.topic,
            instructions=project.research_instructions or "",
            questions=list(project.research_questions or []),
            domain=project.domain,
            llm=None,
        )
        # Latest stored artifacts, so a project overview can show what exists even
        # when the most recent run was cancelled and produced nothing new.
        latest_citations = (
            await session.execute(
                select(CitationReport)
                .where(CitationReport.project_id == project_id)
                .order_by(CitationReport.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        latest_draft = (
            await session.execute(
                select(Draft)
                .where(Draft.project_id == project_id)
                .order_by(Draft.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            **out.model_dump(),
            "settings": project.settings_json or {},
            "citation_summary": (latest_citations.report_json or {}).get("summary")
            if latest_citations
            else None,
            "draft_version": latest_draft.version if latest_draft else None,
            "draft_word_count": len((latest_draft.markdown or "").split()) if latest_draft else 0,
            "draft_status": latest_draft.status if latest_draft else None,
            "runs": [
                {
                    "id": r.id,
                    "status": r.status,
                    "stage": r.stage,
                    "topic": r.topic,
                    "created_at": iso(r.created_at),
                    "finished_at": iso(r.finished_at),
                    "stats": r.stats_json or {},
                    "error": r.error,
                    "stages": stages_from_stats(r.stats_json),
                    "active": workflow_service.is_active(r.id),
                }
                for r in runs
            ],
            "query_plan": plan_preview.as_dict(),
        }


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, payload: ProjectUpdate) -> ProjectOut:
    async with SessionLocal() as session:
        project = await get_project_or_404(session, project_id)
        changes = payload.model_dump(exclude_none=True)
        if "domain" in changes:
            from app.agents.domain import resolve_domain

            changes["domain"] = resolve_domain(changes["domain"], changes.get("topic") or project.topic)
        for field, value in changes.items():
            setattr(project, field, value)
        await session.commit()
        await session.refresh(project)
        return await _project_out(session, project)


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict[str, Any]:
    """Cascade-delete a project and every artefact derived from it."""
    async with SessionLocal() as session:
        project = await get_project_or_404(session, project_id)
        for model in (PaperVector, ResearchGap, ResearchIdea, Collaborator, RadarResult):
            await session.execute(delete(model).where(model.project_id == project_id))
        await session.delete(project)
        await session.commit()
    return {"deleted": project_id}


@router.get("/{project_id}/summary")
async def project_summary(project_id: str) -> dict[str, Any]:
    """Counts used by the dashboard tiles."""
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)

        async def count(model, where=None):
            stmt = select(func.count(model.id)).where(model.project_id == project_id)
            return (await session.execute(stmt)).scalar_one()

        return {
            "papers": await count(Paper),
            "gaps": await count(ResearchGap),
            "ideas": await count(ResearchIdea),
            "drafts": await count(Draft),
            "runs": await count(WorkflowRun),
            "collaborators": await count(Collaborator),
        }


@router.get("/{project_id}/queries")
async def project_queries(project_id: str, refresh: bool = True) -> dict[str, Any]:
    """Preview the search queries that a run would send to the three sources.

    Proves the separation of fields: the topic is short, the brief is context only,
    and every dispatched query is validated to be under 400 characters.
    """
    from app.services.llm import get_llm

    async with SessionLocal() as session:
        project = await get_project_or_404(session, project_id)
        plan = await plan_queries(
            topic=project.topic,
            instructions=project.research_instructions or "",
            questions=list(project.research_questions or []),
            domain=project.domain,
            llm=get_llm() if refresh else None,
        )
    return {"project_id": project_id, "topic": project.topic, **plan.as_dict()}
