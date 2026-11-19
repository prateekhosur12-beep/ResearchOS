"""What actually goes over the wire to OpenAlex / Crossref / arXiv.

These tests exist because of the original defect: the whole multi-paragraph brief
was sent as ``queries[0]`` and rejected by the APIs for exceeding 400 characters.
"""

from __future__ import annotations

import pytest

from app.agents.discovery import LiteratureDiscoveryAgent
from app.runtime.runtime import AgentRuntime
from app.tools.runner import ToolRunner

LONG_BRIEF = (
    "Please act as a research assistant and write a full literature review. Focus on field-scale studies "
    "that combine remote sensing, weather and soil data with machine learning. Prefer work from 2018 "
    "onwards, prefer studies reporting RMSE/MAE/R2 on named datasets, exclude pure classification papers, "
    "exclude policy pieces, and make sure to compare against at least two baselines. " * 3
)


@pytest.mark.asyncio
async def test_every_planned_query_is_dispatched(fake_scholar, project, monkeypatch):
    """The plan is not decoration: each planned query must reach the tools."""
    sent: list[str] = []
    original = ToolRunner.call

    async def recording_call(self, tool, args, **kwargs):  # noqa: ANN001
        if tool.startswith("search_"):
            q = (args or {}).get("query")
            if q:
                sent.append(q)
        return await original(self, tool, args, **kwargs)

    monkeypatch.setattr(ToolRunner, "call", recording_call)

    runtime = AgentRuntime(run_id="plan-dispatch", project_id=project.id)
    tools = ToolRunner(project_id=project.id, run_id=None, transport="direct", record=False)
    await tools.start()
    agent = LiteratureDiscoveryAgent(runtime, tools, project.id)
    result = await agent.run(
        "Road anomaly detection using YOLO",
        {"result_limit": 6, "min_papers": 500, "max_attempts": 1, "domain": "computer_science"},
    )
    await tools.aclose()

    planned = result.stats["queries"]
    assert len(planned) >= 3, planned
    # three sources per query, one query batch
    assert len(sent) >= 3 * len(planned)
    assert set(planned) <= set(sent), f"planned but never sent: {set(planned) - set(sent)}"
    for q in sent:
        assert len(q) < 400, f"query too long for the APIs: {len(q)} chars"
    # records from all queries were merged, not just the first
    assert result.stats["unique_records"] >= 1 and result.papers


@pytest.mark.asyncio
async def test_the_brief_is_never_sent_as_a_query(fake_scholar, monkeypatch):
    sent: list[str] = []
    original = ToolRunner.call

    async def recording_call(self, tool, args, **kwargs):  # noqa: ANN001
        if tool.startswith("search_"):
            q = (args or {}).get("query")
            if q:
                sent.append(q)
        return await original(self, tool, args, **kwargs)

    monkeypatch.setattr(ToolRunner, "call", recording_call)

    project_id = "brief-project"
    runtime = AgentRuntime(run_id="brief-run", project_id=project_id)
    tools = ToolRunner(project_id=project_id, run_id=None, transport="direct", record=False)
    await tools.start()
    agent = LiteratureDiscoveryAgent(runtime, tools, project_id)
    result = await agent.run(
        "Precision agriculture yield prediction",
        {
            "result_limit": 5,
            "min_papers": 500,
            "max_attempts": 1,
            "domain": "agriculture",
            "research_instructions": LONG_BRIEF,
            "research_questions": [
                "Which sensors are used for crop yield prediction?",
                "How are models evaluated?",
            ],
        },
    )
    await tools.aclose()

    assert sent, "no search was dispatched"
    for q in sent:
        assert len(q) <= 400
        assert "Please act as a research assistant" not in q
        assert q not in LONG_BRIEF
    assert max(len(q) for q in sent) < 200
    assert result.stats["unique_records"] >= 0  # the run completed honestly either way
    assert all(len(h.get("queries") or []) >= 1 for h in result.stats["execution_history"])


@pytest.mark.asyncio
async def test_retry_does_not_accumulate_queries(fake_scholar, project):
    """Three attempts must not mean three times the queries in the final tally."""
    runtime = AgentRuntime(run_id="retry-run", project_id=project.id)
    tools = ToolRunner(project_id=project.id, run_id=None, transport="direct", record=False)
    await tools.start()
    agent = LiteratureDiscoveryAgent(runtime, tools, project.id)
    result = await agent.run(
        "Road anomaly detection using YOLO",
        {"result_limit": 5, "min_papers": 500, "max_attempts": 3, "domain": "computer_science"},
    )
    await tools.aclose()

    assert result.stats["attempts"] == 3
    dispatched = result.stats["queries"]
    assert len(dispatched) == len(set(dispatched)), f"duplicate queries in the tally: {dispatched}"
    # A retry replaces the query set instead of appending to it.
    per_attempt = [len(h.get("queries") or [h["query"]]) for h in result.history]
    assert per_attempt[1] == 1 and per_attempt[2] == 1, per_attempt
