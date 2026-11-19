"""Agent 4 — Citation and Compliance Agent.

What it checks (and reports honestly):
  * DOI existence via a live Crossref/OpenAlex lookup — metadata verification only
  * duplicate bibliography entries
  * in-text markers with no bibliography entry (missing)
  * bibliography entries never cited (unused)
  * author / year / title disagreement between the draft and the resolving record

What it deliberately does NOT do:
  * it never claims a source *supports* a claim — that is claim-level evidence
    checking and is marked `not_evaluated` in every report
  * it produces no composite "compliance score"
"""

from __future__ import annotations

import asyncio
import re
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import CitationReport
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.tools.runner import ToolRunner

log = get_logger("agents.citation")


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


class CitationComplianceAgent:
    name = "CitationComplianceAgent"

    def __init__(self, runtime: AgentRuntime, tools: ToolRunner) -> None:
        self.runtime = runtime
        self.tools = tools

    async def run(
        self,
        *,
        project_id: str,
        draft: dict[str, Any],
        bibliography: list[dict[str, Any]],
    ) -> dict[str, Any]:
        await self.runtime.progress("citation_audit", "Auditing references against live DOI registry", agent=self.name)
        markdown = draft.get("markdown") or ""
        markers = sorted(set(re.findall(r"\[(P\d+)\]", markdown)))
        keys = {e["key"] for e in bibliography}

        missing = [m for m in markers if m not in keys]
        unused = [k for k in sorted(keys) if f"[{k}]" not in markdown]

        # Duplicate detection on DOI and on normalised title.
        seen_doi: dict[str, list[str]] = {}
        seen_title: dict[str, list[str]] = {}
        for e in bibliography:
            if e.get("doi"):
                seen_doi.setdefault(e["doi"].lower(), []).append(e["key"])
            seen_title.setdefault(_norm(e.get("title")), []).append(e["key"])
        duplicates = [
            {"kind": "doi", "value": k, "keys": v} for k, v in seen_doi.items() if len(v) > 1
        ] + [{"kind": "title", "value": k, "keys": v} for k, v in seen_title.items() if len(v) > 1]

        # Live DOI verification (bounded concurrency).
        sem = asyncio.Semaphore(4)
        verified: list[dict[str, Any]] = []

        async def check(entry: dict[str, Any]) -> dict[str, Any]:
            base = {
                "key": entry["key"],
                "paper_id": entry.get("paper_id"),
                "title": entry["title"],
                "doi": entry.get("doi"),
                "year": entry.get("year"),
                "cited_in_text": f"[{entry['key']}]" in markdown,
                "metadata_check": "not_run",
                "issues": [],
            }
            if not entry.get("doi"):
                base["metadata_check"] = "unavailable"
                base["issues"].append("no DOI for this record — metadata cannot be verified automatically")
                return base
            async with sem:
                res = await self.tools.call("lookup_doi", {"doi": entry["doi"]})
            self.runtime.stats.tool_calls += 1
            if not res.get("found"):
                base["metadata_check"] = "failed"
                base["issues"].append(
                    f"DOI did not resolve ({res.get('checked_with')}: "
                    f"{res.get('error') or res.get('status')})"
                )
                return base
            rec = res.get("record") or {}
            base["metadata_check"] = "verified"
            base["resolved_via"] = res.get("checked_with")
            base["resolved"] = {
                "title": rec.get("title"),
                "year": rec.get("year"),
                "venue": rec.get("venue"),
                "authors": [a.get("name") for a in (rec.get("authors") or [])][:5],
            }
            title_sim = SequenceMatcher(None, _norm(entry["title"]), _norm(rec.get("title"))).ratio()
            if title_sim < 0.75:
                base["issues"].append(
                    f"title differs from the registered DOI metadata (similarity {title_sim:.2f})"
                )
            base["title_similarity"] = round(title_sim, 3)
            if entry.get("year") and rec.get("year") and abs(int(entry["year"]) - int(rec["year"])) > 1:
                base["issues"].append(
                    f"year mismatch: draft says {entry['year']}, registry says {rec['year']}"
                )
            draft_authors = {_norm(a.get("name")) for a in (entry.get("authors") or []) if a.get("name")}
            reg_authors = {_norm(a.get("name")) for a in (rec.get("authors") or []) if a.get("name")}
            if draft_authors and reg_authors and not (draft_authors & reg_authors):
                base["issues"].append("no author surname/name matches the registry record")
            return base

        verified = list(await asyncio.gather(*(check(e) for e in bibliography)))

        summary = {
            "references": len(bibliography),
            "in_text_markers": len(markers),
            "doi_verified": sum(1 for v in verified if v["metadata_check"] == "verified"),
            "doi_failed": sum(1 for v in verified if v["metadata_check"] == "failed"),
            "doi_unavailable": sum(1 for v in verified if v["metadata_check"] == "unavailable"),
            "missing_bibliography_entries": missing,
            "unused_bibliography_entries": unused,
            "duplicates": duplicates,
            "entries_with_issues": sum(1 for v in verified if v["issues"]),
        }

        report = {
            "run_id": self.runtime.run_id,
            "draft_id": draft.get("id"),
            "draft_version": draft.get("version"),
            "summary": summary,
            "entries": verified,
            "claim_level_evidence_check": "not_evaluated",
            "statement": (
                "Metadata verification confirms that a DOI resolves and that title/year/authors "
                "broadly agree. It does NOT show that the source supports any specific claim in "
                "the manuscript. Claim-level checking requires reading the cited text and is out "
                "of scope for this automated audit."
            ),
            "checks_not_performed": [
                "claim-to-source entailment",
                "quotation accuracy",
                "self-citation policy",
                "journal-specific style compliance beyond the configured formatter",
            ],
        }

        async with SessionLocal() as session:
            session.add(
                CitationReport(
                    project_id=project_id,
                    run_id=self.runtime.run_id,
                    report_json=report,
                    checked=summary["doi_verified"],
                    failed=summary["doi_failed"],
                )
            )
            await session.commit()

        await self.runtime.emit(
            "citation_report_ready",
            stage="citation_audit",
            verified=summary["doi_verified"],
            failed=summary["doi_failed"],
            missing=len(missing),
            unused=len(unused),
            duplicates=len(duplicates),
        )
        warnings = []
        if summary["doi_failed"]:
            warnings.append(
                f"{summary['doi_failed']} reference(s) could not be resolved against Crossref/OpenAlex."
            )
        if missing:
            warnings.append(f"{len(missing)} in-text marker(s) have no bibliography entry: {missing}")
        if unused:
            warnings.append(f"{len(unused)} bibliography entr(ies) are never cited: {unused}")
        return {"report": report, "warnings": warnings}

    async def latest(self, project_id: str) -> dict[str, Any] | None:
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(CitationReport)
                    .where(CitationReport.project_id == project_id)
                    .order_by(CitationReport.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        return row.report_json if row else None
