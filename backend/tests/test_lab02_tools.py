"""Lab 2 — Tool-using agent: validated tools, recorded execution."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import ToolInvocation
from app.tools.impl import compare_papers, read_research_file
from app.tools.registry import ToolNotFound, ToolValidationError, get_registry
from app.tools.runner import ToolRunner


def test_registry_exposes_schemas():
    reg = get_registry()
    names = set(reg.names())
    for expected in {
        "search_openalex",
        "search_crossref",
        "search_arxiv",
        "search_all_sources",
        "lookup_doi",
        "get_paper_details",
        "compare_papers",
        "retrieve_project_memory",
        "save_research_results",
        "generate_research_report",
        "read_research_file",
        "find_topic_funders",
        "verify_venue",
        "find_collaborators",
    }:
        assert expected in names
    schema = next(t for t in reg.describe() if t["name"] == "search_openalex")["input_schema"]
    assert schema["required"] == ["query"]
    assert schema["properties"]["limit"]["maximum"] == 50


def test_argument_validation_rejects_bad_input():
    reg = get_registry()
    with pytest.raises(ToolValidationError):
        reg.validate("search_openalex", {"query": ""})
    with pytest.raises(ToolValidationError):
        reg.validate("search_openalex", {"query": "ok", "limit": 999})
    with pytest.raises(ToolValidationError):
        reg.validate("lookup_doi", {"doi": "x"})
    with pytest.raises(ToolNotFound):
        reg.validate("delete_everything", {})


@pytest.mark.asyncio
async def test_runner_records_validation_failures():
    runner = ToolRunner(project_id=None, run_id=None, transport="direct")
    await runner.start()
    res = await runner.call("search_openalex", {"query": ""})
    await runner.aclose()
    assert res["status"] == "invalid_args"
    assert runner.invocations[0]["status"] == "invalid"

    async with SessionLocal() as s:
        rows = (await s.execute(select(ToolInvocation))).scalars().all()
    assert rows and rows[-1].status == "invalid"


@pytest.mark.asyncio
async def test_runner_propagates_source_failures(fake_scholar):
    fake_scholar.fail_sources = {"crossref"}
    runner = ToolRunner(transport="direct")
    await runner.start()
    res = await runner.call("search_crossref", {"query": "road anomaly"})
    ok = await runner.call("search_openalex", {"query": "road anomaly"})
    await runner.aclose()
    assert res["status"] == "error" and res["count"] == 0
    assert ok["status"] == "ok" and ok["count"] > 0
    assert ok["records"][0]["title"]
    assert ok["retrieved_at"]


@pytest.mark.asyncio
async def test_compare_papers_is_deterministic_and_bounded():
    papers = [
        {
            "id": "a",
            "title": "A YOLO based road anomaly detector",
            "abstract": "We propose a YOLO model for road anomaly detection. A limitation is the lack of "
            "cross-city generalisation. Evaluated on the RDD2022 dataset with 91% accuracy.",
            "year": 2024,
            "venue": "CV Journal",
            "sources": ["crossref"],
        },
        {
            "id": "b",
            "title": "Transformer approaches to anomaly detection",
            "abstract": "A survey of transformer methods. Future work should address latency.",
            "year": 2025,
            "venue": "Survey Journal",
            "sources": ["openalex"],
        },
    ]
    out = await compare_papers({"topic": "road anomaly detection", "papers": papers})
    assert out["count"] == 2
    row_a = out["rows"][0]
    assert "cnn" in row_a["method_signals"]
    assert "RDD2022" in row_a["datasets"]
    assert any("limitation" in s.lower() for s in row_a["limitation_sentences"])
    assert out["summary"]["papers_with_limitations"] == 2
    # same input -> same output (no randomness, no model)
    again = await compare_papers({"topic": "road anomaly detection", "papers": papers})
    assert again["rows"] == out["rows"]


@pytest.mark.asyncio
async def test_read_research_file_blocks_traversal(tmp_path):
    res = await read_research_file({"rel_path": "../../etc/passwd"})
    assert res["ok"] is False and "path rejected" in res["error"]
    res = await read_research_file({"rel_path": "/etc/passwd"})
    assert res["ok"] is False
    res = await read_research_file({"rel_path": "does_not_exist.md"})
    assert res["ok"] is False and "not found" in res["error"]
