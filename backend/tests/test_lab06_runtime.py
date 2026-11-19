"""Lab 6 — Agent runtime: timing, retries, tracing, cancellation, audit chain."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, update

from app.db.base import SessionLocal
from app.db.models import AuditRecord, TraceEvent, WorkflowRun
from app.runtime.runtime import AgentRuntime, RunCancelled, verify_audit_chain


async def _run(project) -> str:
    async with SessionLocal() as s:
        run = WorkflowRun(id=uuid.uuid4().hex, project_id=project.id, topic=project.topic)
        s.add(run)
        await s.commit()
        return run.id


@pytest.mark.asyncio
async def test_step_records_success_and_failure(project):
    run_id = await _run(project)
    rt = AgentRuntime(run_id=run_id, project_id=project.id, max_retries=1)

    ok = await rt.step("TestAgent", "ok_step", lambda: asyncio.sleep(0, result=42))
    assert ok.ok and ok.value == 42 and ok.duration_ms >= 0

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return "recovered"

    res = await rt.step("TestAgent", "flaky_step", flaky)
    assert res.ok and res.value == "recovered" and res.attempts == 2
    assert rt.stats.retries == 1

    always = await rt.step("TestAgent", "failing_step", lambda: _boom())
    assert always.ok is False and "boom" in always.error
    assert rt.stats.failed_steps >= 1

    async with SessionLocal() as s:
        rows = (
            await s.execute(select(TraceEvent).where(TraceEvent.run_id == run_id).order_by(TraceEvent.seq))
        ).scalars().all()
    statuses = [r.status for r in rows]
    assert "ok" in statuses and "error" in statuses
    assert all(r.duration_ms is not None for r in rows)
    assert [r.seq for r in rows] == sorted(r.seq for r in rows)


async def _boom():
    raise ValueError("boom")


@pytest.mark.asyncio
async def test_cancellation_stops_the_next_step(project):
    run_id = await _run(project)
    rt = AgentRuntime(run_id=run_id, project_id=project.id)
    rt.cancel()
    with pytest.raises(RunCancelled):
        await rt.step("TestAgent", "never_runs", lambda: asyncio.sleep(0, result=1))


@pytest.mark.asyncio
async def test_audit_chain_detects_tampering(project):
    run_id = await _run(project)
    rt = AgentRuntime(run_id=run_id, project_id=project.id)
    await rt.audit("run_started", {"topic": "x"})
    await rt.audit("approval_requested", {"approval_id": "abc"})
    await rt.audit("export_created", {"kind": "papers_csv"})

    chain = await verify_audit_chain(project.id)
    assert chain["valid"] is True and chain["records"] == 3

    # Tamper with the payload of the middle record.
    async with SessionLocal() as s:
        await s.execute(
            update(AuditRecord)
            .where(AuditRecord.project_id == project.id, AuditRecord.seq == 2)
            .values(payload_json={"approval_id": "TAMPERED"})
        )
        await s.commit()

    broken = await verify_audit_chain(project.id)
    assert broken["valid"] is False
    assert broken["broken_at_seq"] == 2


@pytest.mark.asyncio
async def test_runtime_never_marks_failed_run_successful(project):
    run_id = await _run(project)
    rt = AgentRuntime(run_id=run_id, project_id=project.id)
    await rt.update_run(status="failed", error="boom")
    async with SessionLocal() as s:
        run = await s.get(WorkflowRun, run_id)
    assert run.status == "failed"
    assert run.stats_json["runtime"]["steps"] == 0
