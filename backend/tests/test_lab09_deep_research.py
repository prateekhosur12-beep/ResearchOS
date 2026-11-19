"""Lab 9 — Deep research: decomposition, extra retrieval, evidence-linked report."""

from __future__ import annotations

import pytest

from app.agents.deep_research import DeepResearchAgent
from app.runtime.runtime import AgentRuntime
from app.tools.runner import ToolRunner


def _paper(i: int, abstract: str | None = "We propose a YOLO detector. A limitation is cross-city "
                                        "generalisation. Evaluated on RDD2022 with 91% accuracy.") -> dict:
    return {
        "id": f"p{i}",
        "title": f"Road anomaly detection paper {i}",
        "abstract": abstract,
        "year": 2020 + i,
        "venue": "CV Journal",
        "doi": f"10.1000/p{i}",
        "url": f"https://example.org/p{i}",
        "sources": ["openalex"],
    }


@pytest.mark.asyncio
async def test_deep_research_produces_evidence_linked_report(fake_scholar):
    rt = AgentRuntime(run_id="dr", project_id="proj")
    tools = ToolRunner(project_id="proj", run_id=None, transport="direct", record=False)
    await tools.start()
    agent = DeepResearchAgent(rt, tools)

    papers = [_paper(i) for i in range(5)]
    gaps = [
        {
            "title": "Cross-city generalisation",
            "description": "Models are tuned per city.",
            "kind": "evidence_backed",
            "confidence": 0.6,
            "evidence_paper_ids": ["p1", "p2"],
        },
        {
            "title": "Method diversity is thin",
            "description": "Cross-paper pattern.",
            "kind": "hypothesis",
            "confidence": 0.4,
            "evidence_paper_ids": ["p3"],
        },
    ]
    matrix = [
        {"title": p["title"], "method_signals": ["cnn"], "datasets": ["RDD2022"], "limitations": ["cross-city"]}
        for p in papers
    ]
    res = await agent.run(
        project_id="proj", topic="road anomaly detection", papers=papers, gaps=gaps, matrix=matrix
    )
    await tools.aclose()

    assert len(res["subquestions"]) >= 3
    assert res["extra_papers_found"] >= 1, "should retrieve additional evidence for sub-questions"
    assert res["report_markdown"].startswith("# Deep Research Report")
    assert "## 7. Remaining uncertainties" in res["report_markdown"]
    assert "Cross-city generalisation" in res["report_markdown"]
    # no invented evidence: every line in the evidence table cites a record
    assert "| # | Paper | Year | Venue | ID |" in res["report_markdown"]
    assert res["uncertainties"]
    assert any("hypothes" in u.lower() for u in res["uncertainties"])


@pytest.mark.asyncio
async def test_deep_research_states_thin_evidence_as_uncertainty(fake_scholar):
    rt = AgentRuntime(run_id="dr2", project_id="proj")
    tools = ToolRunner(transport="direct", record=False)
    await tools.start()
    agent = DeepResearchAgent(rt, tools)
    res = await agent.run(
        project_id="proj",
        topic="very narrow topic",
        papers=[_paper(0, abstract=None)],
        gaps=[],
        matrix=[],
        max_extra_searches=1,
    )
    await tools.aclose()
    joined = " ".join(res["uncertainties"]).lower()
    assert "provisional" in joined or "abstracts" in joined or "not read" in joined
    assert any("no dataset names" in p.lower() or "dataset" in p.lower() for p in res["patterns"])


@pytest.mark.asyncio
async def test_deep_research_uses_model_only_when_available(fake_scholar, fake_ollama):
    fake_ollama["chat"] = {
        "patterns": ["Model says: CNN dominates."],
        "uncertainties": ["Model says: unclear."],
        "subquestion_answers": [{"subquestion": "What methods dominate?", "answer": "CNN per the records."}],
    }
    rt = AgentRuntime(run_id="dr3", project_id="proj")
    tools = ToolRunner(transport="direct", record=False)
    await tools.start()
    agent = DeepResearchAgent(rt, tools)
    res = await agent.run(
        project_id="proj",
        topic="road anomaly detection",
        papers=[_paper(i) for i in range(3)],
        gaps=[],
        matrix=[],
        max_extra_searches=0,
    )
    await tools.aclose()
    assert res["generated_by"].startswith("ollama:")
    assert "### Model-assisted synthesis" in res["report_markdown"]
    assert any("model-generated" in w for w in res["warnings"])
