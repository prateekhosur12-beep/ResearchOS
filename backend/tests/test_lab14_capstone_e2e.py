"""Lab 14 — Capstone studio: the complete, topic-specific workflow end to end.

Mocked external services, real orchestration: project → live-style discovery →
gaps → deep research → ideas → draft → citation audit → radar → collaborators →
approval gate → exports. Two different topics are run to prove results are not
hardcoded and that projects stay isolated.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.agents.export import ExportAgent
from app.db.base import SessionLocal
from app.db.models import (
    Approval,
    CitationReport,
    Collaborator,
    Draft,
    ExportRecord,
    Paper,
    Project,
    RadarResult,
    ResearchGap,
    ResearchIdea,
    SourceAttempt,
    ToolInvocation,
    WorkflowRun,
)
from app.services.workflow_service import WorkflowService

CONFIG = {
    "result_limit": 8,
    "min_papers": 3,
    "generate_draft": True,
    "run_radar": True,
    "run_collaboration": True,
    "max_attempts": 2,
}


async def _new_project(topic: str) -> str:
    async with SessionLocal() as s:
        p = Project(id=uuid.uuid4().hex, name=topic[:40], topic=topic, domain="computer_science")
        s.add(p)
        await s.commit()
        return p.id


async def _run(project_id: str, topic: str) -> str:
    service = WorkflowService()
    run = await service.create_run(project_id, topic, CONFIG)
    await service._execute(run["id"], project_id, topic, CONFIG, "computer_science")
    return run["id"]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_complete_studio_workflow(fake_scholar):
    topic = "Road anomaly detection using YOLO"
    pid = await _new_project(topic)
    run_id = await _run(pid, topic)

    async with SessionLocal() as s:
        run = await s.get(WorkflowRun, run_id)
        papers = (await s.execute(select(Paper).where(Paper.project_id == pid))).scalars().all()
        gaps = (await s.execute(select(ResearchGap).where(ResearchGap.project_id == pid))).scalars().all()
        ideas = (await s.execute(select(ResearchIdea).where(ResearchIdea.project_id == pid))).scalars().all()
        drafts = (await s.execute(select(Draft).where(Draft.project_id == pid))).scalars().all()
        citations = (await s.execute(select(CitationReport).where(CitationReport.project_id == pid))).scalars().all()
        radar = (await s.execute(select(RadarResult).where(RadarResult.project_id == pid))).scalars().all()
        collabs = (await s.execute(select(Collaborator).where(Collaborator.project_id == pid))).scalars().all()
        attempts = (await s.execute(select(SourceAttempt).where(SourceAttempt.run_id == run_id))).scalars().all()
        tools = (await s.execute(select(ToolInvocation).where(ToolInvocation.run_id == run_id))).scalars().all()
        approvals = (await s.execute(select(Approval).where(Approval.project_id == pid))).scalars().all()

    # --- 1. workflow reached the human gate with real artefacts -------------
    assert run.status == "awaiting_approval"
    assert papers and len(papers) >= 3
    assert gaps and all(g.evidence_paper_ids for g in gaps), "every gap must cite papers"
    assert ideas
    assert drafts and drafts[0].markdown.startswith("#")
    assert citations and citations[0].report_json["summary"]["references"] >= 1
    assert radar and collabs
    assert approvals and approvals[0].status == "pending"

    # --- 2. per-source reports exist and the swarm never faked success ------
    assert {a.source for a in attempts} == {"openalex", "crossref", "arxiv"}
    assert all(a.status in ("ok", "empty") for a in attempts)
    assert all(a.latency_ms is not None for a in attempts)

    # --- 3. tools really ran, with a transport recorded --------------------
    tool_names = {t.tool for t in tools}
    assert {"search_openalex", "search_crossref", "search_arxiv", "save_research_results"} <= tool_names
    assert {t.transport for t in tools} <= {"mcp", "direct"}

    # --- 4. drafts cite only retrieved records -----------------------------
    bib = drafts[0].sections_json["bibliography"]
    stored_ids = {p.id for p in papers}
    assert all(b["paper_id"] in stored_ids for b in bib), "bibliography must reference stored papers"
    assert "No experiments were executed" in drafts[0].markdown

    # --- 5. export is gated, then permitted -------------------------------
    exporter = ExportAgent()
    from app.agents.export import ApprovalRequired

    with pytest.raises(ApprovalRequired):
        await exporter.export(project_id=pid, kind="manuscript_md")

    async with SessionLocal() as s:
        approval = (await s.execute(select(Approval).where(Approval.project_id == pid))).scalar_one()
        approval.status = "approved"
        approval.actor = "test-reviewer"
        await s.commit()

    for kind, suffix in [
        ("papers_csv", ".csv"),
        ("gaps_md", ".md"),
        ("manuscript_md", ".md"),
        ("manuscript_docx", ".docx"),
        ("citations_csv", ".csv"),
        ("full_report_md", ".md"),
    ]:
        res = await exporter.export(project_id=pid, kind=kind)
        assert res["filename"].endswith(suffix)
        assert res["size_bytes"] > 0

    async with SessionLocal() as s:
        exports = (await s.execute(select(ExportRecord).where(ExportRecord.project_id == pid))).scalars().all()
    assert len(exports) == 6


@pytest.mark.asyncio
@pytest.mark.slow
async def test_two_topics_produce_different_results_and_stay_isolated(fake_scholar):
    topic_a = "Road anomaly detection using YOLO"
    topic_b = "Federated learning for IoT security"
    pid_a = await _new_project(topic_a)
    pid_b = await _new_project(topic_b)
    await _run(pid_a, topic_a)
    await _run(pid_b, topic_b)

    async with SessionLocal() as s:
        papers_a = (await s.execute(select(Paper).where(Paper.project_id == pid_a))).scalars().all()
        papers_b = (await s.execute(select(Paper).where(Paper.project_id == pid_b))).scalars().all()
        draft_b = (await s.execute(select(Draft).where(Draft.project_id == pid_b))).scalars().all()

    assert papers_a and papers_b
    assert not ({p.id for p in papers_a} & {p.id for p in papers_b}), "projects must not share records"
    # the mock echoes the query into titles, so titles prove topic-specific search
    assert all(topic_a.split()[0].lower() in p.title.lower() for p in papers_a)
    assert all("federated" in p.title.lower() for p in papers_b)
    assert topic_a not in draft_b[0].markdown
    assert topic_b in draft_b[0].markdown

    # the outgoing queries differ per project
    fake_scholar.calls.clear()
    pid_c = await _new_project("Graph neural networks for molecules")
    await _run(pid_c, "Graph neural networks for molecules")
    queries = {c[2].get("search") or c[2].get("query.bibliographic") for c in fake_scholar.calls}
    assert any(q and "molecule" in q.lower() for q in queries), queries
    assert not any(q and "yolo" in q.lower() for q in queries)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_partial_source_failure_still_completes_with_warning(fake_scholar):
    fake_scholar.fail_sources = {"crossref"}
    topic = "Multimodal deep learning for medical imaging"
    pid = await _new_project(topic)
    run_id = await _run(pid, topic)

    async with SessionLocal() as s:
        run = await s.get(WorkflowRun, run_id)
        papers = (await s.execute(select(Paper).where(Paper.project_id == pid))).scalars().all()
        attempts = (await s.execute(select(SourceAttempt).where(SourceAttempt.run_id == run_id))).scalars().all()

    assert papers, "healthy sources must still deliver records"
    assert run.stats_json["failed_sources"] == ["crossref"]
    assert any(a.status == "error" for a in attempts)
    assert run.status in ("awaiting_approval", "partial")
    assert any("crossref" in w for w in run.stats_json["warnings"])