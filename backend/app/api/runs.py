"""Research run endpoints: start, inspect, stream, cancel (Labs 1, 6, 7, 8)."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import create_manual_run, get_project_or_404, get_run_or_404, iso
from app.db.base import SessionLocal
from app.db.models import SourceAttempt, ToolInvocation, TraceEvent, WorkflowRun
from app.events import bus
from app.schemas.models import RunConfig
from app.services.stages import stages_from_stats
from app.services.workflow_service import RunConflict, workflow_service

router = APIRouter(prefix="/api", tags=["runs"])

TERMINAL = {"run_finished", "run_failed", "run_cancelled"}


@router.post("/projects/{project_id}/runs")
async def start_run(project_id: str, payload: RunConfig) -> dict[str, Any]:
    """Start one research run for a project.

    The topic (short title) is the only thing that reaches the search tools; the
    project's brief and questions travel in the run config for the agents.
    """
    async with SessionLocal() as session:
        project = await get_project_or_404(session, project_id)
        topic = project.topic
        domain = project.domain
    config = payload.model_dump()
    try:
        run = await workflow_service.create_run(project_id, topic, config)
    except RunConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "run_already_active",
                "message": str(exc),
                "active_run_id": exc.run_id,
                "active_status": exc.status,
                "hint": f"POST /api/runs/{exc.run_id}/cancel, then start a new run",
            },
        ) from exc
    workflow_service.start(run["id"], project_id, topic, config, domain)
    return {**run, "stream": f"/api/runs/{run['id']}/events"}


@router.get("/projects/{project_id}/runs")
async def list_runs(project_id: str, limit: int = 20) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == project_id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(min(limit, 100))
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "topic": r.topic,
                "status": r.status,
                "stage": r.stage,
                "created_at": iso(r.created_at),
                "finished_at": iso(r.finished_at),
                "stats": r.stats_json or {},
                "error": r.error,
                "active": workflow_service.is_active(r.id),
                "stages": stages_from_stats(r.stats_json),
            }
            for r in rows
        ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    try:
        return await workflow_service.run_status(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cancel a run end to end (cooperative token + task cancellation).

    Idempotent and safe to call on finished runs: the response always says what
    actually happened, and a cancelled run is never reported as completed/failed.
    """
    reason = str((payload or {}).get("reason") or "cancelled by user")[:200]
    try:
        result = await workflow_service.request_cancel(run_id, reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return result


@router.get("/runs/{run_id}/trace")
async def run_trace(run_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        run = await get_run_or_404(session, run_id)
        trace = (
            await session.execute(
                select(TraceEvent).where(TraceEvent.run_id == run_id).order_by(TraceEvent.seq.asc())
            )
        ).scalars().all()
        tools = (
            await session.execute(
                select(ToolInvocation)
                .where(ToolInvocation.run_id == run_id)
                .order_by(ToolInvocation.created_at.asc())
            )
        ).scalars().all()
        attempts = (
            await session.execute(
                select(SourceAttempt)
                .where(SourceAttempt.run_id == run_id)
                .order_by(SourceAttempt.attempt_no.asc(), SourceAttempt.source.asc())
            )
        ).scalars().all()
        return {
            "run": {
                "id": run.id,
                "status": run.status,
                "stage": run.stage,
                "topic": run.topic,
                "stats": run.stats_json or {},
                "error": run.error,
                "created_at": iso(run.created_at),
                "finished_at": iso(run.finished_at),
                "stages": stages_from_stats(run.stats_json),
            },
            "steps": [
                {
                    "seq": t.seq,
                    "agent": t.agent,
                    "step": t.step,
                    "status": t.status,
                    "duration_ms": t.duration_ms,
                    "detail": t.detail_json,
                    "at": iso(t.created_at),
                }
                for t in trace
            ],
            "tool_invocations": [
                {
                    "tool": t.tool,
                    "transport": t.transport,
                    "status": t.status,
                    "latency_ms": t.latency_ms,
                    "summary": t.result_summary,
                    "error": t.error,
                    "args": t.args_json,
                    "at": iso(t.created_at),
                }
                for t in tools
            ],
            "source_attempts": [
                {
                    "attempt": a.attempt_no,
                    "source": a.source,
                    "query": a.query,
                    "status": a.status,
                    "records": a.records,
                    "latency_ms": a.latency_ms,
                    "http_status": a.http_status,
                    "error": a.error,
                    "execution_mode": a.execution_mode,
                    "retrieved_at": iso(a.retrieved_at),
                }
                for a in attempts
            ],
        }


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    """Server-Sent Events carrying real workflow events (no simulated progress)."""

    async def gen() -> AsyncIterator[str]:
        queue = bus.subscribe(run_id)
        last_seq = 0
        try:
            history = bus.history(run_id)
            for event in history:
                last_seq = max(last_seq, int(event.get("seq", 0)))
                yield _sse(event)
            if bus.is_finished(run_id) or any(e.get("type") in TERMINAL for e in history):
                yield _sse({"type": "stream_end", "run_id": run_id})
                return
            idle = 0.0
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    idle += 15
                    yield ": keep-alive\n\n"
                    if idle > 300:
                        yield _sse({"type": "stream_timeout", "run_id": run_id})
                        return
                    continue
                if int(event.get("seq", 0)) <= last_seq:
                    continue
                last_seq = int(event.get("seq", 0))
                yield _sse(event)
                if event.get("type") in TERMINAL:
                    yield _sse({"type": "stream_end", "run_id": run_id})
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.get("/projects/{project_id}/tool-invocations")
async def project_tool_invocations(project_id: str, limit: int = 100) -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(ToolInvocation)
                .where(ToolInvocation.project_id == project_id)
                .order_by(ToolInvocation.created_at.desc())
                .limit(min(limit, 500))
            )
        ).scalars().all()
        return [
            {
                "tool": r.tool,
                "transport": r.transport,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "summary": r.result_summary,
                "error": r.error,
                "args": r.args_json,
                "run_id": r.run_id,
                "at": iso(r.created_at),
            }
            for r in rows
        ]
