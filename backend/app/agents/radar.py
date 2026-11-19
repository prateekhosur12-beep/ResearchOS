"""Agent 5 — Funding and Journal Radar Agent.

Everything returned here is either (a) a venue verified against Crossref's journal
registry, or (b) funder/ award metadata recorded on real publications. Nothing is
invented: no deadlines, no amounts, no impact factors, no acceptance rates.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import delete

from app.agents.domain import get_domain
from app.db.base import SessionLocal
from app.db.models import RadarResult
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.tools.runner import ToolRunner

log = get_logger("agents.radar")


class FundingJournalAgent:
    name = "FundingJournalAgent"

    def __init__(self, runtime: AgentRuntime, tools: ToolRunner) -> None:
        self.runtime = runtime
        self.tools = tools

    async def run(
        self,
        *,
        project_id: str,
        topic: str,
        papers: list[dict[str, Any]],
        domain: str = "computer_science",
        max_venues: int = 5,
    ) -> dict[str, Any]:
        await self.runtime.progress("radar", "Checking venues and funding signals", agent=self.name)
        profile = get_domain(domain)

        venue_counts = Counter(
            (p.get("venue") or "").strip() for p in papers if (p.get("venue") or "").strip()
        )
        candidate_venues = [v for v, _ in venue_counts.most_common(max_venues)]

        journals: list[dict[str, Any]] = []
        for venue in candidate_venues:
            res = await self.tools.call("verify_venue", {"name": venue, "limit": 3})
            self.runtime.stats.tool_calls += 1
            best = res.get("best_match")
            journals.append(
                {
                    "venue_in_literature": venue,
                    "papers_in_corpus": venue_counts[venue],
                    "verification": (best or {}).get("verification", "unverified"),
                    "verified_title": (best or {}).get("title"),
                    "publisher": (best or {}).get("publisher"),
                    "issn": (best or {}).get("issn"),
                    "similarity": (best or {}).get("similarity"),
                    "doi_count_total": (best or {}).get("doi_count_total"),
                    "source_url": (best or {}).get("source_url"),
                    "note": (
                        "Verified: near-exact title match in the Crossref journal registry "
                        "(title/ISSN/publisher). Impact factor and acceptance rate are not "
                        "available from these sources."
                        if (best or {}).get("verification") == "verified"
                        else (
                            "NOT confirmed. The closest Crossref registry entry matches only "
                            f"loosely (similarity {(best or {}).get('similarity', 0)}); conference "
                            "proceedings and books usually have no journal record."
                            if best
                            else "Crossref returned no matching journal record; treat this venue as unverified."
                        )
                    ),
                }
            )
            await self.runtime.emit(
                "venue_checked",
                stage="radar",
                venue=venue,
                verification=(best or {}).get("verification", "unverified"),
            )

        funder_res = await self.tools.call("find_topic_funders", {"query": topic, "limit": 8})
        self.runtime.stats.tool_calls += 1

        suggestions = {
            "target_venues_from_domain_pack": profile.venue_hints,
            "formatting_standard": profile.formatting_standard,
            "note": (
                "Domain-pack venue hints are generic disciplinary guidance, not verified calls for "
                "papers. Only entries marked 'verified' were confirmed against a registry."
            ),
        }

        radar = {
            "journals": journals,
            "funders_in_literature": funder_res.get("funders_in_literature", []),
            "funder_directory_matches": funder_res.get("funder_directory_matches", []),
            "funding_coverage": funder_res.get("coverage", {}),
            "funding_status": funder_res.get("status"),
            "funding_error": funder_res.get("error"),
            "funding_disclaimer": funder_res.get("disclaimer"),
            "venue_suggestions": suggestions,
        }
        await self._persist(project_id, journals, funder_res, profile.venue_hints)
        await self.runtime.emit(
            "radar_ready",
            stage="radar",
            venues=len(journals),
            verified_venues=sum(1 for j in journals if j["verification"] == "verified"),
            funders=len(radar["funders_in_literature"]),
        )
        return radar

    async def _persist(
        self,
        project_id: str,
        journals: list[dict[str, Any]],
        funder_res: dict[str, Any],
        hints: list[str],
    ) -> None:
        async with SessionLocal() as session:
            await session.execute(
                delete(RadarResult).where(
                    RadarResult.project_id == project_id, RadarResult.run_id == self.runtime.run_id
                )
            )
            for j in journals:
                session.add(
                    RadarResult(
                        project_id=project_id,
                        run_id=self.runtime.run_id,
                        kind="journal",
                        name=j.get("verified_title") or j["venue_in_literature"],
                        payload_json=j,
                        verification=j["verification"],
                        source_url=j.get("source_url"),
                    )
                )
            for f in funder_res.get("funders_in_literature", []):
                session.add(
                    RadarResult(
                        project_id=project_id,
                        run_id=self.runtime.run_id,
                        kind="funding",
                        name=f.get("funder", "unknown"),
                        payload_json=f,
                        verification="verified",
                        source_url=f.get("papers", [{}])[0].get("url") if f.get("papers") else None,
                    )
                )
            await session.commit()
