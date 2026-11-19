"""Shared FastAPI dependencies and small helpers."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SessionLocal
from app.db.models import Project, WorkflowRun


async def get_project_or_404(session: AsyncSession, project_id: str) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


async def get_run_or_404(session: AsyncSession, run_id: str) -> WorkflowRun:
    run = await session.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


def iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


async def create_manual_run(project_id: str, label: str) -> str:
    """Manual operations (re-audit, regenerate) get their own run row so that every
    trace entry has a real parent and the audit trail stays complete."""
    async with SessionLocal() as session:
        project = await session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        run = WorkflowRun(
            id=uuid.uuid4().hex,
            project_id=project_id,
            topic=project.topic,
            status="running",
            stage=label,
            config_json={"manual_operation": label},
            stats_json={},
        )
        session.add(run)
        await session.commit()
        return run.id
