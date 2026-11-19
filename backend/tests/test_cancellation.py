"""Run cancellation, end to end (Part 2 of the improvement brief).

Covers the four moments the brief asks for: immediately after start, during the
scholarly search, during a long agent step, and after the run already finished.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import AuditRecord, Draft, Paper, Project, WorkflowRun
from app.runtime.runtime import AgentRuntime, RunCancelled
from app.services.workflow_service import RunConflict, WorkflowService
from app.services.stages import stages_from_stats

CONFIG = {
    "result_limit": 5,
    "min_papers": 3,
    "generate_draft": True,
    "run_radar": False,
    "run_collaboration": False,
    "max_attempts": 1,
}


async def _project(topic: str = "cancellation fixture topic") -> str:
    async with SessionLocal() as s:
        p = Project(id=uuid.uuid4().hex, name=topic[:40], topic=topic, domain="computer_science")
        s.add(p)
        await s.commit()
        return p.id


async def _status(run_id: str) -> tuple[str, dict]:
    async with SessionLocal() as s:
        run = await s.get(WorkflowRun, run_id)
        return run.status, (run.stats_json or {})


@pytest.fixture(autouse=True)
async def no_orphan_tasks():
    """A cancelled/abandoned run task must not outlive its test.

    Without this, a background workflow started here can still be alive when a
    later test opens a ``TestClient``, whose event-loop shutdown would then block
    waiting for it.
    """
    yield
    pending = [
        t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()
    ]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def fast_grace(monkeypatch):
    """Cancellation must not wait the production grace period inside tests."""
    monkeypatch.setattr(settings, "cancel_grace_seconds", 0.5, raising=False)


@pytest.mark.asyncio
async def test_runtime_check_cancelled_raises():
    rt = AgentRuntime(run_id="x", project_id="p")
    rt.check_cancelled()  # no-op before cancellation
    rt.cancel("unit test")
    assert rt.cancelled and rt.cancel_reason == "unit test"
    with pytest.raises(RunCancelled):
        rt.check_cancelled()

    async def never():
        return 1

    with pytest.raises(RunCancelled):
        await rt.step("A", "step", never)


@pytest.mark.asyncio
async def test_cancel_immediately_after_start(monkeypatch):
    """Cancelling before the first node runs leaves the run cancelled, not failed."""
    pid = await _project("quantum error correction codes")
    service = WorkflowService()
    run = await service.create_run(pid, "quantum error correction codes", CONFIG)
    service.start(run["id"], pid, "quantum error correction codes", CONFIG, "computer_science")

    result = await service.request_cancel(run["id"], "user pressed cancel immediately")
    assert result["requested"] is True
    status, stats = await _status(run["id"])
    assert status == "cancelled", result
    assert stats["cancel_reason"] == "user pressed cancel immediately"
    assert "cancelled_at" in stats

    # nothing downstream ran
    async with SessionLocal() as s:
        papers = (await s.execute(select(Paper).where(Paper.project_id == pid))).scalars().all()
        drafts = (await s.execute(select(Draft).where(Draft.project_id == pid))).scalars().all()
    assert papers == [] and drafts == []


@pytest.mark.asyncio
async def test_cancel_during_scholarly_search(monkeypatch):
    """The long pole is the network swarm; cancelling there must stop the run."""
    pid = await _project("sustainable battery recycling")
    service = WorkflowService()
    started = asyncio.Event()

    async def slow_search(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)  # stands in for a slow API; never returns
        raise AssertionError("should have been cancelled")

    monkeypatch.setattr("app.agents.discovery.search_all", slow_search)

    run = await service.create_run(pid, "sustainable battery recycling", CONFIG)
    service.start(run["id"], pid, "sustainable battery recycling", CONFIG, "computer_science")
    await asyncio.wait_for(started.wait(), timeout=10)

    result = await service.request_cancel(run["id"], "search was too slow")
    status, stats = await _status(run["id"])
    assert result["requested"] is True
    assert status == "cancelled"
    assert stats["cancel_reason"] == "search was too slow"
    assert stats.get("pending_artifacts"), "the cancelled run must report what it did not produce"

    stages = {s["key"]: s for s in stages_from_stats(stats)}
    assert stages["understand_topic"]["status"] == "completed"
    assert stages["search_sources"]["status"] == "cancelled"
    assert stages["drafting"]["status"] == "pending"
    assert service.is_active(run["id"]) is False


@pytest.mark.asyncio
async def test_cancel_during_agent_step_is_recorded_in_audit(monkeypatch):
    pid = await _project("blockchain identity")
    service = WorkflowService()
    search_done = asyncio.Event()
    # let discovery finish so a later agent step is the one being cancelled
    monkeypatch.setattr("app.agents.deep_research.DeepResearchAgent.run", _slow_deep(search_done))

    run = await service.create_run(pid, "blockchain identity", CONFIG)
    service.start(run["id"], pid, "blockchain identity", CONFIG, "computer_science")
    await asyncio.wait_for(search_done.wait(), timeout=30)

    await service.request_cancel(run["id"], "cancelled during analysis")
    status, stats = await _status(run["id"])
    assert status == "cancelled"
    assert stats["cancel_reason"] == "cancelled during analysis"

    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(AuditRecord).where(AuditRecord.project_id == pid).order_by(AuditRecord.seq)
            )
        ).scalars().all()
    actions = [r.action for r in rows]
    assert "run_cancelled" in actions
    payload = next(r.payload_json for r in rows if r.action == "run_cancelled")
    assert payload["reason"] == "cancelled during analysis"
    assert "cancelled_at" in payload


def _slow_deep(flag: asyncio.Event):
    async def run(self, **kwargs):
        flag.set()
        await asyncio.sleep(60)
        return {"subquestions": [], "report_markdown": ""}

    return run


@pytest.mark.asyncio
async def test_cancel_after_completion_is_a_no_op(fake_scholar):
    """A finished run must not be relabelled cancelled."""
    pid = await _project("contrastive learning for medical imaging")
    service = WorkflowService()
    run = await service.create_run(pid, "contrastive learning for medical imaging", CONFIG)
    await service._execute(
        run["id"], pid, "contrastive learning for medical imaging", CONFIG, "computer_science"
    )
    status_before, _ = await _status(run["id"])
    assert status_before == "awaiting_approval"

    result = await service.request_cancel(run["id"], "too late")
    assert result["requested"] is False
    assert result["cancelled"] is False
    status_after, stats = await _status(run["id"])
    assert status_after == status_before
    assert "cancel_reason" not in stats


@pytest.mark.asyncio
async def test_second_cancel_request_is_idempotent(monkeypatch):
    pid = await _project("robot manipulation")
    service = WorkflowService()
    started = asyncio.Event()

    async def slow_search(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr("app.agents.discovery.search_all", slow_search)
    run = await service.create_run(pid, "robot manipulation", CONFIG)
    service.start(run["id"], pid, "robot manipulation", CONFIG, "computer_science")
    await asyncio.wait_for(started.wait(), timeout=10)

    first = await service.request_cancel(run["id"], "first")
    second = await service.request_cancel(run["id"], "second")
    assert first["requested"] is True
    assert second["requested"] is False
    assert second["status"] == "cancelled"
    status, stats = await _status(run["id"])
    assert status == "cancelled"
    assert stats["cancel_reason"] == "first", "the first reason wins; no double bookkeeping"


@pytest.mark.asyncio
async def test_second_run_is_refused_while_one_is_active(monkeypatch):
    pid = await _project("crop yield prediction")
    service = WorkflowService()
    started = asyncio.Event()

    async def slow_search(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr("app.agents.discovery.search_all", slow_search)
    run = await service.create_run(pid, "crop yield prediction", CONFIG)
    service.start(run["id"], pid, "crop yield prediction", CONFIG, "computer_science")
    await asyncio.wait_for(started.wait(), timeout=10)

    with pytest.raises(RunConflict) as excinfo:
        await service.create_run(pid, "crop yield prediction", CONFIG)
    assert excinfo.value.run_id == run["id"]

    await service.request_cancel(run["id"], "cleanup")


@pytest.mark.asyncio
async def test_source_swarm_propagates_cancellation_instead_of_reporting_a_failed_source():
    """A cancelled search must not be recorded as 'openalex failed'."""
    from app.services.scholarly.aggregator import search_all
    from app.runtime.runtime import RunCancelled

    async def call(tool, args, **kwargs):  # noqa: ANN001
        raise AssertionError("no tool may be called once the run is cancelled")

    def boom():
        raise RunCancelled("cancelled by user")

    with pytest.raises(RunCancelled):
        await search_all("topic", call, limit=5, mode="parallel", cancel_check=boom)


@pytest.mark.asyncio
async def test_cancelling_during_search_marks_the_stage_cancelled_not_failed(monkeypatch):
    """The stage timeline has to distinguish 'cancelled' from 'failed'."""
    pid = await _project("edge inference on microcontrollers")
    service = WorkflowService()
    started = asyncio.Event()

    async def search_that_gets_cancelled(*args, **kwargs):
        started.set()
        # emulate the cooperative cancel token firing inside the swarm
        await asyncio.sleep(30)

    monkeypatch.setattr("app.agents.discovery.search_all", search_that_gets_cancelled)
    run = await service.create_run(pid, "edge inference on microcontrollers", CONFIG)
    service.start(run["id"], pid, "edge inference on microcontrollers", CONFIG, "computer_science")
    await asyncio.wait_for(started.wait(), timeout=10)
    await service.request_cancel(run["id"], "stop now")

    _, stats = await _status(run["id"])
    stages = {s["key"]: s for s in stages_from_stats(stats)}
    assert stages["search_sources"]["status"] == "cancelled", stages["search_sources"]
    assert stages["search_sources"]["error"] == "cancelled by user"
