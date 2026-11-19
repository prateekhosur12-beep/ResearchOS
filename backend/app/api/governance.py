"""Human approvals, exports and the tamper-evident audit chain (Labs 12, 14)."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.export import ApprovalRequired, ExportAgent, ExportError
from app.api.deps import create_manual_run, get_project_or_404, iso
from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Approval, AuditRecord, Draft, ExportRecord, WorkflowRun
from app.runtime.runtime import verify_audit_chain
from app.services.workflow_service import workflow_service

router = APIRouter(prefix="/api", tags=["governance"])
exporter = ExportAgent()


# ------------------------------------------------------------------ approvals
@router.get("/projects/{project_id}/approvals")
async def list_approvals(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        rows = (
            await session.execute(
                select(Approval)
                .where(Approval.project_id == project_id)
                .order_by(Approval.requested_at.desc())
            )
        ).scalars().all()
    return {
        "required_before_export": settings.require_approval_before_export,
        "approvals": [
            {
                "id": a.id,
                "run_id": a.run_id,
                "artifact_type": a.artifact_type,
                "artifact_id": a.artifact_id,
                "gate": a.gate,
                "status": a.status,
                "requested_at": iso(a.requested_at),
                "decided_at": iso(a.decided_at),
                "actor": a.actor,
                "note": a.note,
            }
            for a in rows
        ],
    }


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    actor: str = Field(default="reviewer", max_length=96)
    note: str | None = Field(default=None, max_length=2000)


@router.post("/approvals/{approval_id}/decide")
async def decide(approval_id: str, payload: Decision) -> dict[str, Any]:
    async with SessionLocal() as session:
        approval = await session.get(Approval, approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        if approval.status != "pending":
            raise HTTPException(status_code=409, detail=f"approval already {approval.status}")
        approval.status = payload.decision
        approval.actor = payload.actor
        approval.note = payload.note
        approval.decided_at = dt.datetime.now(dt.timezone.utc)

        if approval.artifact_type == "draft" and approval.artifact_id:
            draft = await session.get(Draft, approval.artifact_id)
            if draft is not None:
                draft.status = payload.decision
        run = await session.get(WorkflowRun, approval.run_id) if approval.run_id else None
        if run is not None and run.status == "awaiting_approval":
            run.status = "completed" if payload.decision == "approved" else "rejected"
            run.finished_at = run.finished_at or dt.datetime.now(dt.timezone.utc)
        await session.commit()

        project_id, run_id = approval.project_id, approval.run_id

    # Audit the decision on its own run so the chain entry is attributable.
    audit_run = run_id or await create_manual_run(project_id, "approval")
    from app.runtime.runtime import AgentRuntime

    rt = AgentRuntime(run_id=audit_run, project_id=project_id)
    await rt.audit(
        f"approval_{payload.decision}",
        {
            "approval_id": approval_id,
            "artifact_type": payload.artifact_type if hasattr(payload, "artifact_type") else "draft",
            "actor": payload.actor,
            "note": payload.note,
        },
        actor=payload.actor,
    )
    return {"ok": True, "approval_id": approval_id, "status": payload.decision}


# -------------------------------------------------------------------- exports
class ExportRequest(BaseModel):
    kind: str
    run_id: str | None = None
    force: bool = False


@router.post("/projects/{project_id}/exports")
async def create_export(project_id: str, payload: ExportRequest) -> dict[str, Any]:
    try:
        res = await exporter.export(
            project_id=project_id,
            kind=payload.kind,
            run_id=payload.run_id,
            force=payload.force,
        )
    except ApprovalRequired as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_id = payload.run_id or await create_manual_run(project_id, f"export:{payload.kind}")
    from app.runtime.runtime import AgentRuntime

    rt = AgentRuntime(run_id=run_id, project_id=project_id)
    await rt.audit("export_created", {"kind": payload.kind, "file": res["filename"]})
    return {"ok": True, **res}


@router.get("/projects/{project_id}/exports")
async def list_exports(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        rows = (
            await session.execute(
                select(ExportRecord)
                .where(ExportRecord.project_id == project_id)
                .order_by(ExportRecord.created_at.desc())
            )
        ).scalars().all()
    return {
        "available_kinds": sorted(
            [
                "papers_csv",
                "papers_md",
                "gaps_md",
                "manuscript_md",
                "manuscript_docx",
                "citations_md",
                "citations_csv",
                "radar_md",
                "full_report_md",
            ]
        ),
        "exports": [
            {
                "id": e.id,
                "kind": e.kind,
                "filename": e.filename,
                "size_bytes": e.size_bytes,
                "created_at": iso(e.created_at),
                "download_url": f"/api/exports/{project_id}/{e.filename}",
                "approved_by": e.approved_by,
            }
            for e in rows
        ],
    }


@router.get("/exports/{project_id}/{filename}")
async def download_export(project_id: str, filename: str) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = (settings.export_path / project_id / filename).resolve()
    root = (settings.export_path / project_id).resolve()
    if not str(path).startswith(str(root)) or not path.is_file():
        raise HTTPException(status_code=404, detail="export not found")
    media = "application/octet-stream"
    if filename.endswith(".md"):
        media = "text/markdown"
    elif filename.endswith(".csv"):
        media = "text/csv"
    elif filename.endswith(".docx"):
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=filename)


# ---------------------------------------------------------------------- audit
@router.get("/projects/{project_id}/audit")
async def audit_log(project_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        await get_project_or_404(session, project_id)
        rows = (
            await session.execute(
                select(AuditRecord)
                .where(AuditRecord.project_id == project_id)
                .order_by(AuditRecord.seq.asc())
            )
        ).scalars().all()
    chain = await verify_audit_chain(project_id)
    return {
        "records": [
            {
                "seq": r.seq,
                "action": r.action,
                "actor": r.actor,
                "payload": r.payload_json,
                "prev_hash": r.prev_hash[:12],
                "hash": r.hash[:12],
                "at": iso(r.created_at),
            }
            for r in rows
        ],
        "chain_verification": chain,
        "note": (
            "Each entry commits to the previous entry's SHA-256 hash. Editing, deleting or "
            "reordering rows breaks verification of every later row, which is what makes the log "
            "tamper-EVIDENT. The underlying SQLite file remains writable, so this is not immutable "
            "storage."
        ),
    }


# ----------------------------------------------------------------- stress probe
@router.get("/projects/{project_id}/runs/latest/state")
async def latest_run_state(project_id: str) -> dict[str, Any]:
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
    if run is None:
        return {"exists": False}
    return {
        "exists": True,
        "run": {
            "id": run.id,
            "status": run.status,
            "stage": run.stage,
            "stats": run.stats_json or {},
            "error": run.error,
            "active": workflow_service.is_active(run.id),
        },
    }
