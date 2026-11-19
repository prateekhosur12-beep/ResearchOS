"""Agent 1 — Literature Discovery Agent.

Implements the plan → act → observe → revise loop (Lab 1), executes scholarly tools
through the MCP-backed runner (Lab 2), runs the sources concurrently (Lab 8),
persists to project-scoped storage (Lab 4) and returns the full execution history.

It never substitutes demo records for a failed API. If all sources fail the caller
gets zero papers plus the per-source errors.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.common import paper_to_dict
from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Paper, SourceAttempt, WorkflowRun
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.services.embeddings import index_papers
from app.services.llm import get_llm
from app.services.query_planner import (
    MAX_QUERY_CHARS,
    normalize_query,
    plan_queries,
    sanitize_topic,
)
from app.services.scholarly.aggregator import SearchBundle, search_all
from app.services.scholarly.dedupe import deduplicate
from app.services.scholarly.ranking import build_topic_terms, explain_ranking, tokenize
from app.tools.runner import ToolRunner

log = get_logger("agents.discovery")


class QueryPlan(BaseModel):
    intent: str = ""
    keywords: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    subtopics: list[str] = Field(default_factory=list)


class QueryRevision(BaseModel):
    revised_query: str
    reason: str = ""


@dataclass
class DiscoveryResult:
    papers: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)
    llm_available: bool = False


def _already_used(query: str, used: list[str] | None) -> bool:
    if not used:
        return False
    norm = " ".join(query.lower().split())
    return any(norm == " ".join(u.lower().split()) for u in used)


PLAN_SYSTEM = (
    "You turn a research topic into literature-search queries for OpenAlex, Crossref and arXiv. "
    "Return JSON only. Queries must be plain keyword strings without boolean operators, "
    "each targeting a different facet of the topic."
)


class LiteratureDiscoveryAgent:
    name = "LiteratureDiscoveryAgent"

    def __init__(self, runtime: AgentRuntime, tools: ToolRunner, project_id: str) -> None:
        self.runtime = runtime
        self.tools = tools
        self.project_id = project_id
        self.llm = get_llm()
        self.stages: Any = None   # optional StageTracker, injected by the workflow
        self.last_plan: Any = None

    # --------------------------------------------------------------------- plan
    async def understand(
        self,
        topic: str,
        domain: str = "computer_science",
        instructions: str = "",
        questions: list[str] | None = None,
    ) -> QueryPlan:
        """Turn a research title (+ brief) into validated scholarly search queries.

        The brief is context for the model; it is never a query. Every returned query
        is short, de-duplicated and guaranteed to be under the 400-character limit
        enforced by the tool schemas and by all three source APIs.
        """
        plan = await plan_queries(
            topic=topic,
            instructions=instructions,
            questions=questions,
            domain=domain,
            llm=self.llm,
            max_queries=5,
        )
        self.last_plan = plan
        if plan.generated_by == "ollama":
            self.runtime.stats.llm_calls += 1
        return QueryPlan(
            intent=plan.intent,
            keywords=plan.keywords,
            queries=plan.queries,
            subtopics=plan.subtopics,
        )

    def _heuristic_plan(self, topic: str, domain: str) -> QueryPlan:
        """Local, deterministic plan (kept for direct callers and as a safety net)."""
        clean = sanitize_topic(topic) or "research"
        queries = [clean]
        keywords = [t for t in tokenize(clean)][:8]
        if len(keywords) >= 2:
            queries.append(" ".join(keywords[: max(2, math.ceil(len(keywords) * 0.6))]))
        return QueryPlan(
            intent=f"Find scholarly work about {clean}",
            keywords=keywords,
            queries=[q for q in (normalize_query(x) for x in queries) if q][:4],
            subtopics=[f"{k} approaches" for k in keywords[:4]],
        )

    async def revise(
        self,
        topic: str,
        plan: QueryPlan,
        attempt: int,
        observed: dict[str, Any],
        used: list[str] | None = None,
    ) -> tuple[str, str]:
        """Bounded, explainable query revision (the 'revise' half of Lab 1)."""
        health = await self.llm.health()
        if health.get("available"):
            res = await self.llm.chat_structured(
                [
                    {"role": "system", "content": PLAN_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Topic: {topic}\nAttempt {attempt} returned too few usable records.\n"
                            f"Observed: {observed}\nPrevious queries: {plan.queries}\n\n"
                            "Propose ONE different, broader or reframed query that is likely to "
                            "retrieve more relevant literature. Return JSON: "
                            "{\"revised_query\":\"...\",\"reason\":\"...\"}"
                        ),
                    },
                ],
                QueryRevision,
                temperature=0.3,
                num_predict=200,
            )
            if res.ok and res.data and res.data.revised_query.strip():
                self.runtime.stats.llm_calls += 1
                candidate = normalize_query(res.data.revised_query)
                if candidate and not _already_used(candidate, used):
                    return candidate, res.data.reason or "model-proposed revision"
        # Deterministic fallbacks. Each candidate is validated before dispatch and
        # checked against the queries already sent, so retries never accumulate or
        # repeat a query.
        clean = sanitize_topic(topic)
        core = " ".join(plan.keywords[:3]) or clean
        candidates: list[tuple[str, str]] = []
        for q in plan.queries:
            candidates.append((q, "unused query from the original plan"))
        words = clean.split()
        if len(words) > 3:
            candidates.append(
                (" ".join(words[:-1]), "heuristic: dropped the most specific term to broaden recall")
            )
        candidates.append((f"{core} survey", "heuristic: switched to survey-style query"))
        candidates.append((f"{core} review", "heuristic: review-style query"))
        candidates.append((f"{core} recent advances", "heuristic: recency-oriented reformulation"))
        candidates.append((clean, "heuristic: back to the topic title"))

        for raw, reason in candidates:
            cleaned = normalize_query(raw)
            if cleaned and not _already_used(cleaned, used):
                return cleaned, reason
        # worst case: a truncated, always-valid derivative of the title
        fallback = normalize_query(f"{core} literature") or clean[:MAX_QUERY_CHARS]
        return fallback, "heuristic: bounded fallback query"

    # ---------------------------------------------------------------------- run
    async def run(self, topic: str, config: dict[str, Any]) -> DiscoveryResult:
        started = time.perf_counter()
        llm_health = await self.llm.health()
        self.runtime.llm_available = bool(llm_health.get("available"))
        instructions = str(config.get("research_instructions") or "")
        questions = list(config.get("research_questions") or [])
        self.last_plan = None

        await self.runtime.progress("understanding", "Understanding the research topic", agent=self.name)
        if self.stages:
            await self.stages.start("understand_topic", agent=self.name)
        plan_res = await self.runtime.step(
            self.name,
            "understand_topic",
            lambda: self.understand(
                topic,
                config.get("domain", "computer_science"),
                instructions=instructions,
                questions=questions,
            ),
        )
        plan: QueryPlan = plan_res.value if plan_res.ok else self._heuristic_plan(topic, "computer_science")
        if not plan.queries:
            plan = self._heuristic_plan(topic, "computer_science")
        plan_dict = (self.last_plan.as_dict() if self.last_plan else {}) | {
            "queries": plan.queries,
            "keywords": plan.keywords,
            "intent": plan.intent,
            "subtopics": plan.subtopics,
        }
        await self.runtime.emit(
            "plan_ready",
            stage="understanding",
            queries=plan.queries,
            keywords=plan.keywords,
            subtopics=plan.subtopics,
            intent=plan.intent,
            generated_by=plan_dict.get("generated_by", "heuristic"),
            rejected=plan_dict.get("rejected", []),
            warnings=plan_dict.get("warnings", []),
            topic=topic,
            instructions_chars=len(instructions),
            questions_count=len(questions),
        )
        if self.stages:
            await self.stages.finish(
                "understand_topic",
                queries=len(plan.queries),
                generated_by=plan_dict.get("generated_by", "heuristic"),
            )

        limit = int(config.get("result_limit", settings.default_result_limit))
        per_source = max(5, min(25, math.ceil(limit / 2)))
        min_papers = int(config.get("min_papers", settings.min_papers_for_analysis))
        max_attempts = int(config.get("max_attempts", settings.max_discovery_attempts))

        collected = []
        history: list[dict[str, Any]] = []
        failed_sources: list[str] = []
        warnings: list[str] = list(plan_dict.get("warnings") or [])
        queries_used: list[str] = []
        # The planner produces up to MAX_QUERIES facets; dispatch all of them (bounded
        # by settings.max_search_queries) so the plan is what actually reaches the APIs.
        planned = [
            q for q in (normalize_query(x) for x in (plan.queries or [])) if q
        ] or [normalize_query(sanitize_topic(topic)) or "research"]
        budget = max(1, int(settings.max_search_queries))
        attempt_queries = planned[:budget]

        for attempt in range(1, max_attempts + 1):
            self.runtime.check_cancelled()
            if self.stages:
                await self.stages.start(
                    "search_sources",
                    agent=self.name,
                    queries=attempt_queries,
                    attempt=attempt,
                )
            await self.runtime.progress(
                "searching",
                f"Searching OpenAlex, Crossref and arXiv "
                f"({len(attempt_queries)} queries, attempt {attempt}/{max_attempts})",
                agent=self.name,
                attempt=attempt,
                queries=attempt_queries,
            )

            combined: list[dict[str, Any]] = []
            ok_sources: set[str] = set()
            failed_here: set[str] = set()
            attempt_records: list[Any] = []
            attempt_wall_ms = 0
            for query in attempt_queries:
                self.runtime.check_cancelled()
                bundle: SearchBundle = await search_all(
                    query,
                    self.tools.call,
                    limit=per_source,
                    year_from=config.get("year_from"),
                    year_to=config.get("year_to"),
                    types=config.get("publication_types") or None,
                    mode="parallel",
                    timeout=45,
                    cancel_check=self.runtime.check_cancelled,
                )
                self.runtime.stats.tool_calls += 3
                self.runtime.check_cancelled()
                queries_used.append(query)
                attempt_records.extend(bundle.records)
                attempt_wall_ms += bundle.wall_ms
                await self._persist_attempts(bundle, attempt, config)
                for r in bundle.reports:
                    combined.append({"query": query, **r.as_dict()})
                    if r.status == "ok":
                        ok_sources.add(r.source)
                failed_here |= set(bundle.failed_sources)

            collected.extend(attempt_records)
            bundle_failed = sorted(failed_here)
            all_sources = {r["source"] for r in combined}

            if self.stages:
                await self.stages.finish(
                    "search_sources",
                    queries=attempt_queries,
                    sources={
                        "ok": sorted(ok_sources),
                        "failed": bundle_failed,
                        "attempted": sorted(all_sources),
                    },
                )
                await self.stages.start("merge_rank", agent=self.name)
            unique, dstats = deduplicate(collected)
            if self.stages:
                await self.stages.finish("merge_rank", records_raw=len(attempt_records), unique=len(unique))
            attempt_entry = {
                "attempt": attempt,
                "query": attempt_queries[0],
                "queries": list(attempt_queries),
                "per_source": combined,
                "records_raw": len(attempt_records),
                "unique_after_dedupe": len(unique),
                "wall_ms": attempt_wall_ms,
                "dedupe": dstats,
                "successful_sources": sorted(ok_sources),
                "failed_sources": bundle_failed,
            }
            history.append(attempt_entry)
            await self.runtime.emit("search_attempt", stage="searching", **attempt_entry)

            if bundle_failed:
                for src in bundle_failed:
                    warnings.append(f"{src} failed on attempt {attempt}: see per-source report")
                failed_sources = sorted(set(failed_sources) | set(bundle_failed))
            if not ok_sources:
                warnings.append(
                    f"All three sources failed on attempt {attempt}. No records were invented."
                )

            enough = len(unique) >= min_papers
            if enough and ok_sources:
                break
            if attempt == max_attempts:
                warnings.append(
                    f"Bounded revision limit reached ({max_attempts} attempts) with "
                    f"{len(unique)} unique records (target {min_papers})."
                )
                break

            self.runtime.check_cancelled()
            new_query, reason = await self.revise(
                topic,
                plan,
                attempt,
                {"unique_records": len(unique), "failed": bundle_failed},
                used=queries_used,
            )
            attempt_queries = [new_query]
            await self.runtime.emit(
                "query_revised",
                stage="revising",
                previous_query=query,
                revised_query=new_query,
                reason=reason,
                attempt=attempt,
            )
            query = new_query

        await self.runtime.progress("merging", "Merging, deduplicating and ranking records", agent=self.name)
        unique, dstats = deduplicate(collected)
        ranked = self._rank(unique, topic, plan, limit, config)

        save_res = await self.tools.call(
            "save_research_results",
            {
                "project_id": self.project_id,
                "run_id": self.runtime.run_id,
                "topic": topic,
                "papers": [
                    {
                        "source": "+".join(sorted({p.source for p in [r]})),
                        "title": r.title,
                        "doi": r.doi,
                        "arxiv_id": r.arxiv_id,
                        "authors": r.authors,
                        "year": r.year,
                        "venue": r.venue,
                        "abstract": r.abstract,
                        "url": r.url,
                        "pdf_url": r.pdf_url,
                        "cited_by": r.cited_by,
                        "type": r.type,
                        "sources": list(dict.fromkeys(r.source.split("+"))),
                        "warnings": r.warnings,
                    }
                    for r in ranked
                ],
            },
        )
        self.runtime.stats.tool_calls += 1

        papers = await self._load_papers(ranked)
        await self._update_ranking(papers, ranked)

        index_info = {"indexed": 0, "model": "", "note": "skipped"}
        try:
            async with SessionLocal() as session:
                rows = (
                    await session.execute(select(Paper).where(Paper.project_id == self.project_id))
                ).scalars().all()
                index_info = await index_papers(session, self.project_id, rows)
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"semantic index unavailable: {exc}")

        saved = save_res.get("saved", 0)
        stats = {
            "queries": list(dict.fromkeys(queries_used)),
            "attempts": len(history),
            "records_raw": len(collected),
            "unique_records": len(unique),
            "new_records_saved": saved,
            "duplicates_skipped": save_res.get("skipped_duplicates", 0),
            "dedupe": dstats,
            "per_source": history[-1]["per_source"] if history else [],
            "failed_sources": failed_sources,
            "wall_ms": int((time.perf_counter() - started) * 1000),
            "embedding": index_info,
            "min_papers_target": min_papers,
            "target_met": len(papers) >= min_papers,
            "tool_transport": self.tools.mode,
            "llm_available": bool(llm_health.get("available")),
            "llm_detail": llm_health.get("detail", ""),
            "execution_history": history,
        }
        if not papers:
            warnings.append(
                "No papers could be stored. Check the per-source error reports; no fallback data was used."
            )

        return DiscoveryResult(
            papers=[paper_to_dict(p) for p in papers],
            plan=plan.model_dump(),
            stats=stats,
            history=history,
            warnings=warnings,
            failed_sources=failed_sources,
            llm_available=bool(llm_health.get("available")),
        )

    # ------------------------------------------------------------------ helpers
    def _rank(self, records, topic: str, plan: QueryPlan, limit: int, config: dict[str, Any]):
        from app.services.scholarly.records import ScholarlyRecord

        enriched: list[tuple[float, ScholarlyRecord, dict[str, Any]]] = []
        for rec in records:
            explanation = explain_ranking(
                topic=topic,
                queries=plan.queries,
                title=rec.title,
                abstract=rec.abstract,
                year=rec.year,
                cited_by=rec.cited_by,
                sources=rec.source.split("+"),
            )
            enriched.append((explanation["score"], rec, explanation))
        enriched.sort(key=lambda t: -t[0])
        top = enriched[: max(limit * 2, limit + 10)]
        self._explanations = {id(rec): exp for _, rec, exp in enriched}
        return [rec for _, rec, _ in top]

    async def _update_ranking(self, papers: list[Paper], ranked) -> None:
        by_title = {r.norm_title: r for r in ranked}
        explanations = getattr(self, "_explanations", {})
        async with SessionLocal() as session:
            for p in papers:
                rec = by_title.get(p.norm_title)
                if rec is None:
                    continue
                exp = explanations.get(id(rec))
                if exp:
                    p.rank_score = exp["score"]
                    p.rank_explain_json = exp
                    await session.merge(p)
            await session.commit()

    async def _load_papers(self, ranked) -> list[Paper]:
        async with SessionLocal() as session:
            rows = (
                await session.execute(
                    select(Paper).where(Paper.project_id == self.project_id)
                )
            ).scalars().all()
        # keep only papers from this run's records, ordered by rank
        wanted = {r.norm_title for r in ranked}
        selected = [p for p in rows if p.norm_title in wanted]
        selected.sort(key=lambda p: -p.rank_score)
        return selected

    async def _persist_attempts(self, bundle: SearchBundle, attempt: int, config: dict[str, Any]) -> None:
        try:
            async with SessionLocal() as session:
                for r in bundle.reports:
                    session.add(
                        SourceAttempt(
                            run_id=self.runtime.run_id,
                            project_id=self.project_id,
                            attempt_no=attempt,
                            source=r.source,
                            query=r.query or "",
                            status=r.status,
                            http_status=r.http_status,
                            latency_ms=r.latency_ms,
                            records=r.records,
                            error=r.error,
                            execution_mode=self.tools.mode,
                        )
                    )
                run = await session.get(WorkflowRun, self.runtime.run_id)
                if run:
                    run.stage = "discovery"
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to persist source attempts: %s", exc)
