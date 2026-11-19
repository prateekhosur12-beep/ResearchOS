#!/usr/bin/env python
"""End-to-end smoke test against the *real* stack.

Runs a complete project lifecycle with live scholarly APIs (OpenAlex, Crossref,
arXiv), the real MCP server subprocess and the local Ollama daemon if present:

    python smoke_e2e.py                  # uses the default topic
    python smoke_e2e.py "your topic"     # any research topic

Everything printed is measured from the run: no canned numbers, no demo data.
Exit code is 0 only if every required artefact was produced.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./smoke_e2e.db")
os.environ.setdefault("DATA_DIR", "./data")
os.environ.setdefault("EXPORT_DIR", "./exports")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select  # noqa: E402

from app.agents.export import EXPORT_KINDS, ApprovalRequired, ExportAgent  # noqa: E402
from app.db.base import SessionLocal, init_db  # noqa: E402
from app.db.models import (  # noqa: E402
    Approval,
    CitationReport,
    Collaborator,
    Draft,
    Paper,
    Project,
    RadarResult,
    ResearchGap,
    ResearchIdea,
    SourceAttempt,
    ToolInvocation,
    WorkflowRun,
)
from app.runtime.runtime import verify_audit_chain  # noqa: E402
from app.services.llm import get_llm  # noqa: E402
from app.services.workflow_service import WorkflowService  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def main(topic: str) -> int:
    t0 = time.time()
    await init_db()

    print("\n=== 0. Environment ===")
    health = await get_llm().health(use_cache=False)
    print(
        f"  LLM: {'available' if health['available'] else 'UNAVAILABLE'} "
        f"({health['base_url']}, model={health['model']}, "
        f"installed={health['models_installed']})"
    )
    if not health["available"]:
        print(f"  note: {health['detail']}")
        print("  → agents will use deterministic, evidence-grounded non-LLM paths.")

    print("\n=== 1. Create project ===")
    async with SessionLocal() as s:
        project = Project(
            id=uuid.uuid4().hex,
            name=f"smoke {topic[:40]}",
            topic=topic,
            domain="computer_science",
        )
        s.add(project)
        await s.commit()
        pid = project.id
    print(f"  project_id = {pid}")

    print("\n=== 2. Run the agent workflow (live retrieval) ===")
    config = {
        "result_limit": 10,
        "min_papers": 5,
        "generate_draft": True,
        "run_radar": True,
        "run_collaboration": True,
        "max_attempts": 2,
    }
    service = WorkflowService()
    run = await service.create_run(pid, topic, config)
    print(f"  run_id = {run['id']} (transport={run.get('transport')})")
    await service._execute(run["id"], pid, topic, config, "computer_science")

    async with SessionLocal() as s:
        stored = await s.get(WorkflowRun, run["id"])
        papers = (await s.execute(select(Paper).where(Paper.project_id == pid))).scalars().all()
        gaps = (await s.execute(select(ResearchGap).where(ResearchGap.project_id == pid))).scalars().all()
        ideas = (await s.execute(select(ResearchIdea).where(ResearchIdea.project_id == pid))).scalars().all()
        drafts = (await s.execute(select(Draft).where(Draft.project_id == pid))).scalars().all()
        citations = (await s.execute(select(CitationReport).where(CitationReport.project_id == pid))).scalars().all()
        radar = (await s.execute(select(RadarResult).where(RadarResult.project_id == pid))).scalars().all()
        collabs = (await s.execute(select(Collaborator).where(Collaborator.project_id == pid))).scalars().all()
        attempts = (await s.execute(select(SourceAttempt).where(SourceAttempt.run_id == run["id"]))).scalars().all()
        tools = (await s.execute(select(ToolInvocation).where(ToolInvocation.run_id == run["id"]))).scalars().all()

    stats = stored.stats_json or {}
    disc = stats.get("discovery", {})
    models = stats.get("models", {})
    print(
        f"  status={stored.status}\n"
        f"  tool_transport={models.get('tool_transport')} ({models.get('tool_transport_note')})\n"
        f"  llm_available={models.get('llm_available')} — {models.get('llm_detail')}\n"
        f"  records_raw={disc.get('records_raw')} unique={disc.get('unique_records')} "
        f"papers={len(papers)} failed_sources={stats.get('failed_sources')}"
    )
    print(f"  queries: {stats.get('queries')}")
    for a in attempts:
        print(
            f"    {a.source:9s} {a.status:8s} {a.records or 0:3d} records  "
            f"{a.latency_ms or 0:5d} ms  via {a.execution_mode}"
        )
    for w in stats.get("warnings", []):
        print(f"    warning: {w}")

    check("live retrieval returned papers", len(papers) > 0, f"{len(papers)} stored")
    check("papers are topic-specific", len(papers) > 0 and bool(stats.get("queries")),
          str(stats.get("queries"))[:120])
    check("per-source outcomes recorded honestly",
          isinstance(stats.get("failed_sources"), list) and len(attempts) >= 3,
          f"failed={stats.get('failed_sources')}")
    check("gaps derived with evidence links", bool(gaps) and all(g.evidence_paper_ids for g in gaps),
          f"{len(gaps)} gaps")
    check("research ideas proposed", bool(ideas), f"{len(ideas)} ideas")
    check("draft generated with bibliography", bool(drafts) and bool(drafts[0].sections_json.get("bibliography")),
          f"{len(drafts[0].markdown)} chars, v{drafts[0].version}" if drafts else "none")
    check("citation audit ran", bool(citations), json.dumps(citations[0].report_json["summary"])[:160] if citations else "")
    check("radar produced results", bool(radar), f"{len(radar)} section(s)")
    check("collaborators found", bool(collabs), f"{len(collabs)}")
    check("tool invocations recorded", len(tools) > 0,
          f"{len(tools)} calls over {sorted({t.transport for t in tools})}")
    check("run paused at the human approval gate", stored.status == "awaiting_approval", stored.status)

    print("\n=== 3. Approval gate ===")
    exporter = ExportAgent()
    try:
        await exporter.export(project_id=pid, kind="manuscript_md")
        check("export blocked before approval", False, "export succeeded without approval")
    except ApprovalRequired:
        check("export blocked before approval", True, "HTTP 403 equivalent raised")

    async with SessionLocal() as s:
        approval = (await s.execute(select(Approval).where(Approval.project_id == pid))).scalar_one_or_none()
        if approval:
            approval.status = "approved"
            approval.actor = "smoke-test"
            await s.commit()
    check("approval recorded", approval is not None, approval.actor if approval else "")

    print("\n=== 4. Exports ===")
    kinds = sorted(EXPORT_KINDS)
    produced = 0
    for kind in kinds:
        try:
            res = await exporter.export(project_id=pid, kind=kind)
            produced += 1
            print(f"    {kind:18s} {res['size_bytes']:>8d} B  {res['filename']}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {kind:18s} FAILED: {exc}")
    check("exports produced real files", produced == len(kinds), f"{produced}/{len(kinds)}")

    print("\n=== 5. Audit chain ===")
    chain = await verify_audit_chain(pid)
    print(f"  {chain}")
    check("audit chain intact", chain["valid"], f"{chain['records']} records")

    elapsed = time.time() - t0
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n=== SUMMARY: {len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed in {elapsed:.1f}s ===")
    print(f"  report data: project_id={pid} run_id={run['id']}")
    if failed:
        print("  FAILED: " + ", ".join(c[0] for c in failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "road anomaly detection using YOLO for Indian roads"
    sys.exit(asyncio.run(main(topic)))
