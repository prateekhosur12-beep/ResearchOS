"""Lab 1 — Agent vs chatbot: plan → act → observe → revise, bounded."""

from __future__ import annotations

import pytest

from app.agents.discovery import LiteratureDiscoveryAgent
from app.runtime.runtime import AgentRuntime
from app.tools.runner import ToolRunner


@pytest.mark.asyncio
async def test_plan_act_observe_revise_loop(fake_scholar, project):
    fake_scholar.empty_sources = set()
    runtime = AgentRuntime(run_id="run-lab1", project_id=project.id)
    # A run id that does not exist in the DB is tolerated by the trace writer.
    tools = ToolRunner(project_id=project.id, run_id=None, transport="direct", record=False)
    await tools.start()

    agent = LiteratureDiscoveryAgent(runtime, tools, project.id)
    result = await agent.run(
        "Road anomaly detection using YOLO",
        {"result_limit": 5, "min_papers": 500, "max_attempts": 3, "domain": "computer_science"},
    )
    await tools.aclose()

    # It kept going until the bound, then stopped with an honest warning.
    assert len(result.history) == 3
    assert any("Bounded revision limit reached" in w for w in result.warnings)

    # Queries actually changed between attempts (this is the 'revise' step).
    queries = [h["query"] for h in result.history]
    assert len(set(queries)) == len(queries), f"queries did not change: {queries}"

    # Observations were recorded per attempt, with per-source status.
    first = result.history[0]
    assert {s["source"] for s in first["per_source"]} == {"openalex", "crossref", "arxiv"}
    assert first["records_raw"] >= 1 and first["unique_after_dedupe"] >= 1
    assert first["wall_ms"] >= 0
    assert result.stats["attempts"] == 3

    # A single-turn chatbot would return one string; here we return the full trace.
    assert result.stats["execution_history"]
    assert all("per_source" in h for h in result.stats["execution_history"])


@pytest.mark.asyncio
async def test_stops_early_when_enough_literature(fake_scholar, project):
    runtime = AgentRuntime(run_id="r2", project_id=project.id)
    tools = ToolRunner(project_id=project.id, run_id=None, transport="direct", record=False)
    await tools.start()
    agent = LiteratureDiscoveryAgent(runtime, tools, project.id)
    result = await agent.run(
        "Federated learning for IoT security",
        {"result_limit": 5, "min_papers": 2, "max_attempts": 3, "domain": "computer_science"},
    )
    await tools.aclose()
    assert len(result.history) == 1, "should stop after the first attempt once the target is met"
    assert result.papers, "papers must be persisted and returned"
    assert result.stats["target_met"] is True


@pytest.mark.asyncio
async def test_total_failure_never_fabricates(fake_scholar, project):
    fake_scholar.fail_sources = {"openalex", "crossref", "arxiv"}
    runtime = AgentRuntime(run_id="r3", project_id=project.id)
    tools = ToolRunner(project_id=project.id, run_id=None, transport="direct", record=False)
    await tools.start()
    agent = LiteratureDiscoveryAgent(runtime, tools, project.id)
    result = await agent.run(
        "Quantum error correction", {"result_limit": 5, "min_papers": 2, "max_attempts": 1}
    )
    await tools.aclose()

    assert result.papers == []
    assert sorted(result.failed_sources) == ["arxiv", "crossref", "openalex"]
    assert any("No records were invented" in w for w in result.warnings)
    assert any("No papers could be stored" in w for w in result.warnings)
