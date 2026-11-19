"""Lab 4 — Memory & retrieval: project isolation, persistence, semantic search."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import Paper, PaperVector, Project
from app.services.embeddings import cosine, index_papers, local_embed, semantic_search
from app.tools.impl import retrieve_project_memory, save_research_results


async def _project(name: str) -> str:
    async with SessionLocal() as s:
        p = Project(id=uuid.uuid4().hex, name=name, topic=name, domain="computer_science")
        s.add(p)
        await s.commit()
        return p.id


def test_local_embedding_is_deterministic_and_normalised():
    a = local_embed("federated learning for iot security")
    b = local_embed("federated learning for iot security")
    c = local_embed("road anomaly detection with yolo")
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-4  # rounded to 6 dp
    assert cosine(a, a) > 0.99
    assert cosine(a, c) < cosine(a, b)


@pytest.mark.asyncio
async def test_papers_are_project_scoped():
    p1 = await _project("project-one")
    p2 = await _project("project-two")

    await save_research_results(
        {
            "project_id": p1,
            "papers": [
                {"title": "Federated learning for IoT security", "doi": "10.1/a", "source": "openalex",
                 "abstract": "privacy preserving aggregation", "sources": ["openalex"]}
            ],
        }
    )
    await save_research_results(
        {
            "project_id": p2,
            "papers": [
                {"title": "Road anomaly detection with YOLO", "doi": "10.1/b", "source": "crossref",
                 "abstract": "pothole detection with convolutional networks", "sources": ["crossref"]}
            ],
        }
    )

    async with SessionLocal() as s:
        a = (await s.execute(select(Paper).where(Paper.project_id == p1))).scalars().all()
        b = (await s.execute(select(Paper).where(Paper.project_id == p2))).scalars().all()
    assert [p.title for p in a] == ["Federated learning for IoT security"]
    assert [p.title for p in b] == ["Road anomaly detection with YOLO"]

    # Semantic retrieval must not cross the boundary.
    async with SessionLocal() as s:
        res1 = await semantic_search(s, p1, "yolo pothole detection", limit=5)
    assert res1["results"], "should find something inside p1"
    assert all(r["title"] != "Road anomaly detection with YOLO" for r in res1["results"])


@pytest.mark.asyncio
async def test_duplicate_papers_are_not_stored_twice():
    pid = await _project("dedupe")
    payload = {
        "project_id": pid,
        "papers": [
            {"title": "Same paper", "doi": "10.1/same", "source": "openalex", "sources": ["openalex"]},
        ],
    }
    first = await save_research_results(payload)
    second = await save_research_results(payload)
    assert first["saved"] == 1
    assert second["saved"] == 0 and second["skipped_duplicates"] == 1


@pytest.mark.asyncio
async def test_project_memory_tool_reads_only_that_project():
    pid = await _project("memory")
    other = await _project("other")
    await save_research_results(
        {
            "project_id": pid,
            "papers": [
                {"title": "Memory test paper", "doi": "10.1/m", "source": "openalex", "sources": ["openalex"]}
            ],
        }
    )
    res = await retrieve_project_memory({"project_id": pid, "limit": 5})
    assert res["found"] and res["paper_count"] == 1
    assert res["papers"][0]["title"] == "Memory test paper"
    assert res["project"]["topic"] == "memory"

    missing = await retrieve_project_memory({"project_id": "does-not-exist"})
    assert missing["found"] is False

    empty = await retrieve_project_memory({"project_id": other, "limit": 5})
    assert empty["paper_count"] == 0 and empty["papers"] == []


@pytest.mark.asyncio
async def test_vectors_are_indexed_and_rebuildable():
    pid = await _project("vectors")
    await save_research_results(
        {
            "project_id": pid,
            "papers": [
                {"title": "Deep learning for medical imaging", "doi": "10.1/v", "source": "openalex",
                 "abstract": "cnn segmentation", "sources": ["openalex"]}
            ],
        }
    )
    async with SessionLocal() as s:
        papers = (await s.execute(select(Paper).where(Paper.project_id == pid))).scalars().all()
        info = await index_papers(s, pid, papers)
        await s.commit()
        assert info["indexed"] == 1
        vecs = (await s.execute(select(PaperVector).where(PaperVector.project_id == pid))).scalars().all()
        assert len(vecs) == 1 and vecs[0].dim == len(vecs[0].vector_json)
        # re-indexing must update, not duplicate
        await index_papers(s, pid, papers)
        await s.commit()
        vecs2 = (await s.execute(select(PaperVector).where(PaperVector.project_id == pid))).scalars().all()
        assert len(vecs2) == 1
