"""Lab 8 — Parallel agent swarm: concurrency, partial failure, measured comparison."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.scholarly.aggregator import compare_modes, search_all
from app.services.scholarly.dedupe import deduplicate
from app.services.scholarly.records import ScholarlyRecord


def _rec(source: str, title: str, doi: str | None = None, arxiv: str | None = None) -> dict:
    return {
        "source": source,
        "title": title,
        "doi": doi,
        "arxiv_id": arxiv,
        "authors": [{"name": "A. Author"}],
        "year": 2024,
        "venue": "Journal",
        "abstract": "An abstract about road anomaly detection.",
        "url": f"https://example.org/{abs(hash(title)) % 1000}",
        "sources": [source],
    }


def make_caller(delay: float = 0.2, fail: set[str] | None = None):
    fail = fail or set()

    async def caller(tool: str, args: dict) -> dict:
        source = tool.replace("search_", "")
        await asyncio.sleep(delay)
        if source in fail:
            raise RuntimeError(f"{source} is down")
        return {
            "tool": tool,
            "source": source,
            "status": "ok",
            "query": args["query"],
            "latency_ms": int(delay * 1000),
            "retrieved_at": "2026-01-01T00:00:00Z",
            "records": [
                _rec(source, f"{source} paper 1", doi="10.1/shared" if source != "arxiv" else None,
                     arxiv="2401.00001" if source == "arxiv" else None),
                _rec(source, f"{source} paper 2", doi=f"10.1/{source}2"),
            ],
        }

    caller.mode = "test"
    return caller


@pytest.mark.asyncio
async def test_parallel_is_faster_than_sequential_measured():
    seq = await search_all("road anomaly detection", make_caller(0.25), mode="sequential")
    par = await search_all("road anomaly detection", make_caller(0.25), mode="parallel")
    assert seq.wall_ms > par.wall_ms, "sequential must be slower with equal per-source latency"
    assert par.wall_ms < 600, f"parallel wall time too high: {par.wall_ms}ms"
    assert len(par.records) == len(seq.records)


@pytest.mark.asyncio
async def test_partial_failure_keeps_successful_sources():
    bundle = await search_all("road anomaly detection", make_caller(0.01, fail={"crossref"}))
    statuses = {r.source: r.status for r in bundle.reports}
    assert statuses["openalex"] == "ok"
    assert statuses["arxiv"] == "ok"
    assert statuses["crossref"] == "error"
    assert bundle.failed_sources == ["crossref"]
    assert len(bundle.records) == 4, "records from healthy sources must survive"
    assert bundle.any_success and not bundle.all_failed


@pytest.mark.asyncio
async def test_timeout_is_reported_not_hidden():
    async def slow(tool, args):
        await asyncio.sleep(2)
        return {"status": "ok", "records": []}

    slow.mode = "test"
    bundle = await search_all("q", slow, timeout=0.3)
    assert all(r.status == "timeout" for r in bundle.reports)
    assert bundle.all_failed
    assert all("exceeded" in (r.error or "") for r in bundle.reports)


@pytest.mark.asyncio
async def test_dedupe_merges_on_doi_arxiv_and_title():
    records = [
        ScholarlyRecord(source="openalex", title="A Study of Road Anomaly Detection",
                        doi="10.1/x", abstract="abstract from openalex", authors=[{"name": "A"}], year=2024),
        ScholarlyRecord(source="crossref", title="A study of road-anomaly detection.",
                        doi="10.1/x", abstract=None, authors=[{"name": "B"}], year=2024),
        ScholarlyRecord(source="arxiv", title="Different preprint", arxiv_id="2401.1", abstract="preprint abs", year=2024),
        ScholarlyRecord(source="crossref", title="DIFFERENT preprint", doi=None, arxiv_id=None, year=2024),
        ScholarlyRecord(source="openalex", title="Road Anomaly Detection with YOLO", doi="10.1/y", year=2023),
    ]
    merged, stats = deduplicate(records)
    assert stats["input"] == 5
    assert stats["unique"] == 3, [m.title for m in merged]  # doi pair + arxiv/title pair + yolo
    first = next(m for m in merged if m.doi == "10.1/x")
    assert "openalex" in first.source and "crossref" in first.source
    assert first.abstract == "abstract from openalex", "richer metadata must win"
    assert first.warnings is not None


@pytest.mark.asyncio
async def test_compare_modes_reports_real_numbers():
    res = await compare_modes("road anomaly detection", lambda: make_caller(0.15))
    assert res["sequential"]["wall_ms"] > 0 and res["parallel"]["wall_ms"] > 0
    assert res["speedup"] and res["speedup"] > 1
    assert len(res["sequential"]["per_source"]) == 3
