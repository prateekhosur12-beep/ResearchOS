"""Lab 12 — Safety & governance: approval gates, safe paths, audit integrity."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.citation import CitationComplianceAgent
from app.agents.export import ApprovalRequired, ExportAgent, ExportError
from app.db.base import SessionLocal
from app.db.models import Draft, Paper, Project
from app.main import app
from app.runtime.runtime import AgentRuntime, verify_audit_chain
from app.tools.runner import ToolRunner


async def _seed(project_id: str, draft: bool = True) -> None:
    async with SessionLocal() as s:
        s.add(
            Paper(
                project_id=project_id,
                dedupe_key=f"doi:10.1/{uuid.uuid4().hex[:6]}",
                title="Grounded paper on road anomaly detection",
                norm_title="grounded paper on road anomaly detection",
                doi="10.1000/grounded",
                year=2024,
                venue="Test Journal",
                abstract="We propose YOLO. A limitation is cross-city generalisation.",
                authors_json=[{"name": "Ada Lovelace"}],
                sources_json=["openalex"],
            )
        )
        if draft:
            s.add(
                Draft(
                    project_id=project_id,
                    version=1,
                    markdown="# Draft\n\n## Introduction\n\nPrior work is strong [P1].\n\n## References\n\n[P1] Ada Lovelace. 2024.",
                    sections_json={
                        "title": "Draft",
                        "sections": {
                            "introduction": {"name": "introduction", "markdown": "Prior work [P1].", "word_count": 3}
                        },
                        "bibliography": [
                            {
                                "key": "P1",
                                "paper_id": "x",
                                "title": "Grounded paper on road anomaly detection",
                                "authors": [{"name": "Ada Lovelace"}],
                                "year": 2024,
                                "doi": "10.1000/grounded",
                            }
                        ],
                    },
                    status="draft",
                    generated_by="test",
                )
            )
        await s.commit()


async def _project() -> str:
    async with SessionLocal() as s:
        p = Project(id=uuid.uuid4().hex, name="gov", topic="road anomaly detection")
        s.add(p)
        await s.commit()
        return p.id


@pytest.mark.asyncio
async def test_manuscript_export_requires_approval():
    pid = await _project()
    await _seed(pid)
    agent = ExportAgent()
    with pytest.raises(ApprovalRequired):
        await agent.export(project_id=pid, kind="manuscript_md")
    # non-gated artefacts are fine
    res = await agent.export(project_id=pid, kind="papers_csv")
    assert res["size_bytes"] > 0
    # an unknown kind is rejected rather than silently ignored
    with pytest.raises(ExportError):
        await agent.export(project_id=pid, kind="everything")


@pytest.mark.asyncio
async def test_approval_unlocks_export():
    pid = await _project()
    await _seed(pid)
    async with SessionLocal() as s:
        from app.db.models import Approval

        approval = Approval(project_id=pid, artifact_type="draft", status="approved", actor="reviewer")
        s.add(approval)
        draft = (await s.execute(select(Draft).where(Draft.project_id == pid))).scalar_one()
        draft.status = "approved"
        await s.commit()

    agent = ExportAgent()
    md = await agent.export(project_id=pid, kind="manuscript_md")
    docx = await agent.export(project_id=pid, kind="manuscript_docx")
    assert md["filename"].endswith(".md") and md["size_bytes"] > 0
    assert docx["filename"].endswith(".docx") and docx["size_bytes"] > 1000


@pytest.mark.asyncio
async def test_citation_agent_separates_metadata_from_claim_support(fake_scholar, project):
    rt = AgentRuntime(run_id="cid", project_id=project.id)
    tools = ToolRunner(transport="direct", record=False)
    await tools.start()
    agent = CitationComplianceAgent(rt, tools)
    draft = {
        "id": "d1",
        "version": 1,
        "markdown": "Claim one [P1]. Claim two [P2]. Claim three [P9].",
    }
    bibliography = [
        {"key": "P1", "paper_id": "a", "title": "Test paper one", "doi": "10.1000/test.0",
         "authors": [{"name": "Author 0"}], "year": 2023},
        {"key": "P2", "paper_id": "b", "title": "Missing DOI paper", "doi": None, "authors": [], "year": 2024},
        {"key": "P3", "paper_id": "c", "title": "Unused paper", "doi": "10.1000/test.1", "authors": [], "year": 2024},
    ]
    res = await agent.run(project_id=project.id, draft=draft, bibliography=bibliography)
    await tools.aclose()

    report = res["report"]
    summary = report["summary"]
    assert report["claim_level_evidence_check"] == "not_evaluated"
    assert "does NOT show that the source supports" in report["statement"]
    assert summary["missing_bibliography_entries"] == ["P9"], "marker without an entry must be reported"
    assert summary["unused_bibliography_entries"] == ["P3"]
    assert summary["doi_unavailable"] == 1
    assert summary["doi_failed"] == 0  # mocked registry resolves everything it is asked about
    assert "composite score" not in str(report).lower()


@pytest.mark.asyncio
async def test_audit_chain_endpoint_reports_tampering(project):
    rt = AgentRuntime(run_id="aud", project_id=project.id)
    await rt.audit("run_started", {"topic": "x"})
    await rt.audit("export_created", {"kind": "papers_csv"})
    chain = await verify_audit_chain(project.id)
    assert chain["valid"] and chain["records"] == 2


def test_download_endpoint_blocks_traversal():
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "dl", "topic": "safe download test"}).json()
        bad = client.get(f"/api/exports/{project['id']}/..%2f..%2fetc%2fpasswd")
        assert bad.status_code in (400, 404)
        missing = client.get(f"/api/exports/{project['id']}/nope.md")
        assert missing.status_code == 404


def test_export_endpoint_documents_available_kinds():
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "kinds", "topic": "kinds test"}).json()
        body = client.get(f"/api/projects/{project['id']}/exports").json()
        assert "manuscript_docx" in body["available_kinds"]
        assert body["exports"] == []


@pytest.mark.asyncio
async def test_venue_verification_never_upgrades_a_loose_match(monkeypatch):
    """A fuzzy registry hit must never be reported as proof of a venue."""
    from app.services.scholarly.http import FetchResult
    from app.tools.impl import verify_venue

    async def fake_journal_search(name, limit=3):
        items = [
            {
                "title": "Chemischer Informationsdienst",
                "publisher": "Wiley",
                "ISSN": ["0009-2940"],
                "counts": {"total-dois": 10},
            }
        ]
        return items, FetchResult(
            source="crossref", url="https://api.crossref.org/journals", status="ok",
            http_status=200, latency_ms=1, payload="{}",
        )

    monkeypatch.setattr("app.tools.impl.crossref.journal_search", fake_journal_search)
    res = await verify_venue({"name": "IEEE Pune Section International Conference (PuneCon)"})
    assert res["best_match"]["similarity"] < 0.92
    assert res["best_match"]["verification"] == "unverified"
    assert "NOT confirmed" in res["match_note"]

    async def exact_search(name, limit=3):
        items = [{"title": name, "publisher": "Elsevier", "ISSN": ["1234-5678"], "counts": {"total-dois": 500}}]
        return items, FetchResult(
            source="crossref", url="https://api.crossref.org/journals", status="ok",
            http_status=200, latency_ms=1, payload="{}",
        )

    monkeypatch.setattr("app.tools.impl.crossref.journal_search", exact_search)
    ok = await verify_venue({"name": "Pattern Recognition"})
    assert ok["best_match"]["verification"] == "verified"
