"""Lab 7 — Agentic node graph: routing, conditional edges, approval pause."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Approval, Draft, Paper, Project, ResearchGap, WorkflowRun
from app.graph.state import ResearchState
from app.graph.workflow import build_graph, route_after_citation, route_after_discovery
from app.services.workflow_service import WorkflowService


def test_route_after_discovery():
    assert route_after_discovery({"papers": []}) == "stop"
    assert route_after_discovery({"papers": [{}] * 2, "config": {"min_papers": 5}}) == "revise"
    assert route_after_discovery({"papers": [{}] * 6, "config": {"min_papers": 5}}) == "gap"
    # revision budget exhausted -> proceed with what we have
    assert (
        route_after_discovery(
            {"papers": [{}] * 2, "config": {"min_papers": 5}, "discovery_revisions": settings.max_graph_revisions}
        )
        == "gap"
    )


def test_route_after_citation():
    assert route_after_citation({"citation_feedback": "P2: DOI did not resolve", "draft_revisions": 0}) == "revise_draft"
    assert route_after_citation({"citation_feedback": None}) == "continue"
    assert (
        route_after_citation(
            {"citation_feedback": "again", "draft_revisions": settings.max_graph_revisions}
        )
        == "continue"
    )


@pytest.mark.asyncio
async def test_graph_compiles_with_typed_state():
    from app.graph.workflow import WorkflowContext
    from app.runtime.runtime import AgentRuntime
    from app.tools.runner import ToolRunner

    rt = AgentRuntime(run_id="x", project_id="y")
    tools = ToolRunner(transport="direct", record=False)
    graph = build_graph(WorkflowContext(rt, tools, "y", "x"))
    nodes = set(graph.get_graph().nodes)
    for expected in {
        "discover",
        "revise_search",
        "gap_analysis",
        "deep_research",
        "ideas",
        "drafting",
        "citation_audit",
        "draft_revision",
        "radar",
        "collaboration",
        "approval",
        "finalize",
        "no_evidence",
    }:
        assert expected in nodes, f"missing node {expected}"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_full_graph_run_pauses_at_human_approval(fake_scholar, project):
    service = WorkflowService()
    config = {
        "result_limit": 6,
        "min_papers": 2,
        "generate_draft": True,
        "run_radar": False,
        "run_collaboration": False,
        "max_attempts": 1,
    }
    run = await service.create_run(project.id, project.topic, config)
    await service._execute(run["id"], project.id, project.topic, config, "computer_science")

    async with SessionLocal() as s:
        stored = await s.get(WorkflowRun, run["id"])
        papers = (await s.execute(select(Paper).where(Paper.project_id == project.id))).scalars().all()
        gaps = (await s.execute(select(ResearchGap).where(ResearchGap.project_id == project.id))).scalars().all()
        drafts = (await s.execute(select(Draft).where(Draft.project_id == project.id))).scalars().all()
        approvals = (await s.execute(select(Approval).where(Approval.project_id == project.id))).scalars().all()

    assert stored.status == "awaiting_approval"
    assert papers and gaps and drafts
    assert len(approvals) == 1 and approvals[0].status == "pending"
    assert stored.stats_json["approval_status"] == "pending"
    # The stage log proves the nodes that actually executed.
    stages = [s["stage"] for s in stored.stats_json["stage_log"]]
    assert "discovery" in stages and "gap_analysis" in stages and "drafting" in stages


@pytest.mark.asyncio
@pytest.mark.slow
async def test_no_evidence_path_fails_loudly(fake_scholar, project):
    fake_scholar.fail_sources = {"openalex", "crossref", "arxiv"}
    service = WorkflowService()
    config = {"result_limit": 5, "min_papers": 2, "generate_draft": False, "max_attempts": 1}
    run = await service.create_run(project.id, project.topic, config)
    await service._execute(run["id"], project.id, project.topic, config, "computer_science")

    async with SessionLocal() as s:
        stored = await s.get(WorkflowRun, run["id"])
        papers = (await s.execute(select(Paper).where(Paper.project_id == project.id))).scalars().all()
    assert stored.status == "failed"
    assert papers == []
    assert any("no scholarly records" in e or "zero records" in e for e in stored.stats_json["errors"])
