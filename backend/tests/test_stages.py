"""Workflow stage reporting (Part 3 of the improvement brief).

Twelve stages, real statuses, real durations, real call counts. No invented
percentages: a stage is only "completed" if the backend actually completed it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.domain import detect_domain, get_domain, resolve_domain
from app.db.base import SessionLocal
from app.db.models import Project, WorkflowRun
from app.main import app
from app.services.stages import STAGE_DEFS, STAGE_KEYS, stages_from_stats
from app.services.workflow_service import WorkflowService

CONFIG = {
    "result_limit": 6,
    "min_papers": 2,
    "generate_draft": True,
    "run_radar": True,
    "run_collaboration": True,
    "max_attempts": 1,
}


def test_stage_definition_is_the_documented_twelve():
    assert [k for k, _, _ in STAGE_DEFS] == [
        "understand_topic",
        "search_sources",
        "merge_rank",
        "gap_analysis",
        "deep_research",
        "ideas",
        "drafting",
        "citation_audit",
        "radar",
        "collaboration",
        "approval",
        "finalize",
    ]


def test_blank_stages_are_pending():
    stages = stages_from_stats({})
    assert len(stages) == 12
    assert {s["status"] for s in stages} == {"pending"}
    assert all(s["started_at"] is None for s in stages)


def test_legacy_runs_get_a_filled_in_stage_list():
    """Older runs only stored a few stages; the API must still answer completely."""
    legacy = {"stages": [{"key": "drafting", "status": "completed"}]}
    stages = stages_from_stats(legacy)
    assert len(stages) == 12
    by_key = {s["key"]: s for s in stages}
    assert by_key["drafting"]["status"] == "completed"
    assert by_key["gap_analysis"]["status"] == "pending"
    assert [s["key"] for s in stages] == STAGE_KEYS


@pytest.mark.asyncio
async def test_full_run_reports_real_stage_statuses_and_timings(fake_scholar):
    async with SessionLocal() as s:
        project = Project(
            id=uuid.uuid4().hex, name="stages", topic="federated learning for iot security",
            domain="computer_science",
        )
        s.add(project)
        await s.commit()
        pid = project.id

    service = WorkflowService()
    run = await service.create_run(pid, project.topic, CONFIG)
    await service._execute(run["id"], pid, project.topic, CONFIG, "computer_science")

    async with SessionLocal() as s:
        stored = await s.get(WorkflowRun, run["id"])
    stages = {x["key"]: x for x in stages_from_stats(stored.stats_json)}

    completed = {
        "understand_topic", "search_sources", "merge_rank", "gap_analysis",
        "deep_research", "ideas", "drafting", "citation_audit", "radar",
        "collaboration", "approval", "finalize",
    }
    assert {k for k, v in stages.items() if v["status"] == "completed"} == completed

    # durations are measured, not fabricated
    for key in ("drafting", "gap_analysis", "search_sources"):
        assert stages[key]["duration_ms"] is not None and stages[key]["duration_ms"] >= 0
    # tool calls are attributed to the stages that made them
    assert stages["search_sources"]["tool_calls"] >= 3
    assert stages["collaboration"]["tool_calls"] >= 1
    # the approval stage records the pending human decision
    assert stages["approval"]["detail"]["decision"] == "pending"


@pytest.mark.asyncio
async def test_disabled_stages_are_reported_as_skipped_not_completed(fake_scholar):
    async with SessionLocal() as s:
        project = Project(
            id=uuid.uuid4().hex, name="skips", topic="graph neural networks", domain="computer_science",
        )
        s.add(project)
        await s.commit()
        pid = project.id

    config = {**CONFIG, "generate_draft": False, "run_radar": False, "run_collaboration": False}
    service = WorkflowService()
    run = await service.create_run(pid, project.topic, config)
    await service._execute(run["id"], pid, project.topic, config, "computer_science")

    async with SessionLocal() as s:
        stored = await s.get(WorkflowRun, run["id"])
    stages = {x["key"]: x for x in stages_from_stats(stored.stats_json)}

    assert stages["drafting"]["status"] == "skipped"
    assert stages["radar"]["status"] == "skipped"
    assert stages["collaboration"]["status"] == "skipped"
    assert "disabled" in stages["drafting"]["detail"]["skip_reason"]
    assert stages["citation_audit"]["status"] == "skipped"  # no draft to audit
    assert stages["gap_analysis"]["status"] == "completed"


def test_run_api_exposes_stages(fake_scholar, monkeypatch):
    # A deliberately slow swarm so cancellation lands while the run is genuinely
    # active (otherwise a mocked run finishes in ~1 s and the test would be racy).
    async def slow_search(*args, **kwargs):
        import asyncio

        await asyncio.sleep(30)

    monkeypatch.setattr("app.agents.discovery.search_all", slow_search)
    with TestClient(app) as client:
        project = client.post(
            "/api/projects", json={"name": "api stages", "topic": "oriented bounding boxes"}
        ).json()
        run = client.post(f"/api/projects/{project['id']}/runs", json={"result_limit": 4}).json()
        # the run executes in a background task; poll briefly for the first writes
        import time

        deadline = time.time() + 30
        stages = []
        while time.time() < deadline:
            detail = client.get(f"/api/runs/{run['id']}").json()
            stages = detail.get("stages") or []
            if any(s["status"] != "pending" for s in stages):
                break
            time.sleep(0.2)
        assert len(stages) == 12
        assert any(s["status"] in ("running", "completed") for s in stages)
        assert {"key", "name", "status", "duration_ms", "tool_calls"} <= set(stages[0])

        # Cancel through the API so no background task outlives the test, and so the
        # endpoint contract (idempotent, honest) is exercised at HTTP level.
        cancelled = client.post(f"/api/runs/{run['id']}/cancel", json={"reason": "test cleanup"}).json()
        assert cancelled["requested"] is True
        detail = client.get(f"/api/runs/{run['id']}").json()
        assert detail["status"] == "cancelled"
        assert detail["error"].startswith("cancelled")
        # cancelling again is a no-op, not an error
        again = client.post(f"/api/runs/{run['id']}/cancel", json={"reason": "again"}).json()
        assert again["requested"] is False
        assert again["status"] == "cancelled"


def test_domain_routing_for_the_three_acceptance_topics():
    assert detect_domain("AI-Driven Precision Agriculture: Crop Yield Prediction") == "agriculture"
    assert (
        detect_domain("Blockchain-Based Digital Identity and Privacy-Preserving Authentication")
        == "cybersecurity"
    )
    assert (
        detect_domain("Sustainable Battery Recycling and Second-Life Energy Storage Systems")
        == "energy"
    )
    assert resolve_domain("auto", "road anomaly detection using YOLO") == "computer_science"
    assert get_domain("agriculture").formatting_standard == "APA"
    assert "RMSE" in " ".join(get_domain("agriculture").evaluation_metrics)
