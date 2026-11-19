"""Agent 2 — Gap and Idea Analysis Agent.

Evidence discipline:
  * every gap carries the ids of the papers that suggest it
  * `evidence_backed` gaps quote the authors' own limitation sentences
  * `hypothesis` gaps are labelled as cross-paper patterns, not facts
  * a gap with no supporting paper is dropped, not published
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from app.agents.domain import get_domain
from app.db.base import SessionLocal
from app.db.models import ResearchGap
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.skills.gap_matrix import GapMatrixSkill
from app.tools.runner import ToolRunner

log = get_logger("agents.gap")


class GapAnalysisAgent:
    name = "GapAnalysisAgent"

    def __init__(self, runtime: AgentRuntime, tools: ToolRunner) -> None:
        self.runtime = runtime
        self.tools = tools
        self.skill = GapMatrixSkill()

    async def run(
        self,
        *,
        project_id: str,
        topic: str,
        papers: list[dict[str, Any]],
        domain: str = "computer_science",
        max_gaps: int = 6,
    ) -> dict[str, Any]:
        await self.runtime.progress("gap_analysis", "Comparing methods, datasets and limitations", agent=self.name)

        usable = [p for p in papers if p.get("title")]
        if not usable:
            return {
                "gaps": [],
                "matrix": [],
                "warnings": ["no papers available — gap analysis skipped rather than fabricated"],
                "generated_by": "none",
            }

        # Tool evidence: deterministic field comparison through the tool layer.
        compare = await self.tools.call(
            "compare_papers",
            {
                "topic": topic,
                "papers": [
                    {
                        "id": p["id"],
                        "title": p["title"],
                        "year": p.get("year"),
                        "venue": p.get("venue"),
                        "doi": p.get("doi"),
                        "abstract": p.get("abstract"),
                        "cited_by": p.get("cited_by"),
                        "sources": p.get("sources", []),
                    }
                    for p in usable[:20]
                ],
            },
        )

        skill_res = await self.skill.run(
            {
                "topic": topic,
                "domain": domain,
                "papers": [
                    {
                        "id": p["id"],
                        "title": p["title"],
                        "abstract": p.get("abstract"),
                        "year": p.get("year"),
                        "venue": p.get("venue"),
                        "doi": p.get("doi"),
                        "url": p.get("url"),
                        "sources": p.get("sources", []),
                    }
                    for p in usable
                ],
                "max_gaps": max_gaps,
            }
        )

        data = skill_res.data or {}
        gaps = data.get("gaps", [])
        matrix = data.get("matrix", [])
        coverage = data.get("coverage", {})

        ids = {p["id"] for p in usable}
        validated = []
        for g in gaps:
            ev = [i for i in g.get("evidence_paper_ids", []) if i in ids]
            if not ev:
                log.warning("dropping ungrounded gap: %s", g.get("title"))
                continue
            g["evidence_paper_ids"] = ev
            validated.append(g)

        domain_profile = get_domain(domain)
        await self._persist(project_id, self.runtime.run_id, validated, domain_profile.evaluation_metrics)

        await self.runtime.emit(
            "gaps_ready",
            stage="gap_analysis",
            count=len(validated),
            evidence_backed=sum(1 for g in validated if g["kind"] == "evidence_backed"),
            hypothesis=sum(1 for g in validated if g["kind"] == "hypothesis"),
            coverage=coverage,
            generated_by=skill_res.generated_by,
        )

        return {
            "gaps": validated,
            "matrix": matrix,
            "coverage": coverage,
            "comparison": {k: v for k, v in (compare or {}).items() if k != "rows"},
            "generated_by": skill_res.generated_by,
            "warnings": skill_res.warnings,
            "llm_used": skill_res.llm_used,
        }

    async def _persist(
        self,
        project_id: str,
        run_id: str,
        gaps: list[dict[str, Any]],
        domain_metrics: list[str],
    ) -> None:
        async with SessionLocal() as session:
            # Gaps are a derived artifact: a new analysis supersedes the previous one.
            # (Ideas behave the same way.) The old run's stats keep their own record.
            await session.execute(
                delete(ResearchGap).where(ResearchGap.project_id == project_id)
            )
            for g in gaps:
                session.add(
                    ResearchGap(
                        project_id=project_id,
                        run_id=run_id,
                        title=g["title"][:500],
                        description=g.get("description", ""),
                        rationale=g.get("rationale", ""),
                        evidence_paper_ids=g.get("evidence_paper_ids", []),
                        evidence_quotes=g.get("evidence_quotes", []),
                        kind=g.get("kind", "hypothesis"),
                        confidence=float(g.get("confidence", 0.0)),
                        feasibility=g.get("feasibility"),
                        suggested_metrics=g.get("suggested_metrics") or domain_metrics[:3],
                    )
                )
            await session.commit()
