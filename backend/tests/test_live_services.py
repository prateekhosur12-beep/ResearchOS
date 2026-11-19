"""Live tests — real network, real APIs, real MCP subprocess.

Skipped by default. Enable with:

    RUN_LIVE_TESTS=1 python -m pytest tests/test_live_services.py -v

These hit OpenAlex / Crossref / arXiv and the local Ollama daemon, so they are
slow and may fail for reasons outside the code (rate limits, offline machine).
They exist to prove the integrations are real rather than mocked.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Paper, Project, WorkflowRun
from app.services.scholarly.aggregator import search_all
from app.services.workflow_service import WorkflowService

pytestmark = pytest.mark.live


@pytest.fixture
async def mcp_caller():
    """Real MCP transport, real network — no mocks anywhere."""
    from app.tools.runner import ToolRunner

    runner = ToolRunner(transport="mcp", record=False)
    await runner.start()
    try:
        yield runner
    finally:
        await runner.aclose()


@pytest.mark.asyncio
async def test_live_sources_return_records_for_a_real_topic(mcp_caller):
    bundle = await search_all(
        "federated learning for IoT security", mcp_caller.call, mode="parallel", limit=5
    )
    statuses = {r.source: r.status for r in bundle.reports}
    assert statuses["openalex"] == "ok", bundle.reports
    ok_sources = [s for s, st in statuses.items() if st == "ok"]
    assert len(ok_sources) >= 2, f"at least two sources should answer, got {statuses}"
    assert bundle.records, "no records retrieved from any live source"
    top = bundle.records[0]
    assert top.title and top.url
    assert all(r.latency_ms is not None for r in bundle.reports if r.status == "ok")


@pytest.mark.asyncio
async def test_live_topic_specificity(mcp_caller):
    a = await search_all("road anomaly detection using YOLO", mcp_caller.call, mode="parallel", limit=5)
    b = await search_all("plant taxonomy of orchids", mcp_caller.call, mode="parallel", limit=5)
    titles_a = {r.title.lower() for r in a.records}
    titles_b = {r.title.lower() for r in b.records}
    assert titles_a and titles_b
    assert titles_a != titles_b
    assert len(titles_a ^ titles_b) > max(len(titles_a), len(titles_b)) * 0.5


@pytest.mark.asyncio
@pytest.mark.slow
async def test_live_full_workflow_is_topic_specific():
    topic = "graph neural networks for molecular property prediction"
    async with SessionLocal() as s:
        project = Project(id=uuid.uuid4().hex, name="live check", topic=topic, domain="computer_science")
        s.add(project)
        await s.commit()
        pid = project.id

    service = WorkflowService()
    config = {
        "result_limit": 5,
        "min_papers": 3,
        "generate_draft": True,
        "run_radar": False,
        "run_collaboration": False,
        "max_attempts": 1,
    }
    run = await service.create_run(pid, topic, config)
    await service._execute(run["id"], pid, topic, config, "computer_science")

    async with SessionLocal() as s:
        stored = await s.get(WorkflowRun, run["id"])
        papers = (await s.execute(select(Paper).where(Paper.project_id == pid))).scalars().all()

    assert stored.status in ("awaiting_approval", "partial", "failed")
    assert stored.stats_json["papers"] == len(papers)
    if papers:
        assert all(p.url or p.doi for p in papers), "every stored record must be traceable"
        assert stored.status == "awaiting_approval"


@pytest.mark.asyncio
async def test_live_ollama_status_is_truthful():
    from app.services.llm import get_llm

    health = await get_llm().health(use_cache=False)
    assert health["base_url"] == settings.ollama_base_url
    assert health["model"] == settings.ollama_model
    if health["available"]:
        assert any(m.startswith(settings.ollama_model.split(":")[0]) for m in health["models_installed"])
    else:
        # An unavailable daemon must be reported, never silently replaced by fake text.
        assert health["detail"]
