"""LangGraph research workflow with conditional routing (Lab 7).

    discovery ──► (too few papers?) ──► revise search (bounded) ──┐
        │                                                          │
        └──────────────► gap analysis ──► deep research ──► ideas ─┘
                                                     │
                        drafting ◄──── (citation failures, bounded)
                            │
                        citation audit
                            │
                  radar ──► collaboration ──► human approval gate
                                                      │
                                              (approved) ──► finalize

The graph is compiled with an in-memory checkpointer. Run state is additionally
persisted to the database after every node, so the UI and an operator can see what
happened. Crash recovery from a checkpoint is NOT claimed.
"""

from __future__ import annotations

import asyncio

import time
from typing import Any, Callable

from langgraph.graph import END, StateGraph

from app.agents.collaboration import CollaborationAgent
from app.agents.deep_research import DeepResearchAgent
from app.agents.discovery import LiteratureDiscoveryAgent
from app.agents.drafting import DraftingAgent
from app.agents.export import ExportAgent
from app.agents.gap import GapAnalysisAgent
from app.agents.radar import FundingJournalAgent
from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Approval
from app.graph.state import ResearchState
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime, RunCancelled
from app.skills.research_question import ResearchQuestionSkill
from app.tools.runner import ToolRunner

log = get_logger("graph")


class WorkflowContext:
    """Everything a node needs, bound once per run."""

    def __init__(
        self,
        runtime: AgentRuntime,
        tools: ToolRunner,
        project_id: str,
        run_id: str,
        stages: Any = None,
    ) -> None:
        self.runtime = runtime
        self.tools = tools
        self.project_id = project_id
        self.run_id = run_id
        self.stages = stages
        self.discovery_stages = stages
        self.discovery = LiteratureDiscoveryAgent(runtime, tools, project_id)
        self.discovery.stages = stages
        self.gap = GapAnalysisAgent(runtime, tools)
        self.deep = DeepResearchAgent(runtime, tools)
        self.drafting = DraftingAgent(runtime, tools)
        from app.agents.citation import CitationComplianceAgent

        self.citation = CitationComplianceAgent(runtime, tools)
        self.radar = FundingJournalAgent(runtime, tools)
        self.collab = CollaborationAgent(runtime, tools)
        self.export = ExportAgent()
        self.rqs = ResearchQuestionSkill()


class _ContextStagesMixin:  # placeholder to keep import tools happy
    pass


def build_graph(ctx: WorkflowContext) -> Any:
    rt = ctx.runtime

    # ---------------------------------------------------------------- stage hooks
    async def stage_start(key: str, **detail: Any) -> None:
        if ctx.stages is not None:
            await ctx.stages.start(key, **detail)

    async def stage_finish(key: str, status: str = "completed", **detail: Any) -> None:
        if ctx.stages is not None:
            await ctx.stages.finish(key, status, **detail)

    async def stage_skip(key: str, reason: str) -> None:
        if ctx.stages is not None:
            await ctx.stages.skip(key, reason)

    async def stage_fail_running(error: str) -> None:
        if ctx.stages is not None:
            await ctx.stages.fail_running(error)

    async def node_discover(state: ResearchState) -> dict[str, Any]:
        cfg = dict(state.get("config") or {})
        cfg["domain"] = state.get("domain", "computer_science")
        if state.get("discovery_revisions", 0) > 0:
            cfg["max_attempts"] = 2
            cfg["min_papers"] = max(1, int(cfg.get("min_papers", 5)) - 1)
        try:
            result = await ctx.discovery.run(state["topic"], cfg)
        except (asyncio.CancelledError, RunCancelled):
            # The run service records the cancellation; a cancelled stage is not a failure.
            raise
        except Exception as exc:
            await stage_fail_running(f"{exc.__class__.__name__}: {exc}")
            raise
        await rt.update_run(stage="discovery")
        return {
            "papers": result.papers,
            "plan": result.plan,
            "queries": result.stats.get("queries", []),
            "discovery_stats": result.stats,
            "failed_sources": result.failed_sources,
            "warnings": list(state.get("warnings", [])) + result.warnings,
            "stage_log": _log(state, "discovery", {"papers": len(result.papers)}),
        }

    async def node_gap(state: ResearchState) -> dict[str, Any]:
        await stage_start("gap_analysis", agent=ctx.gap.name)
        step = await rt.step(
            ctx.gap.name,
            "gap_analysis",
            lambda: ctx.gap.run(
                project_id=ctx.project_id,
                topic=state["topic"],
                papers=state.get("papers", []),
                domain=state.get("domain", "computer_science"),
                max_gaps=int((state.get("config") or {}).get("max_gaps", 6)),
            ),
        )
        res = step.value if step.ok else {"gaps": [], "matrix": [], "warnings": [step.error or "gap analysis failed"]}
        await stage_finish(
            "gap_analysis",
            "completed" if step.ok else "failed",
            error=None if step.ok else step.error,
            gaps=len(res.get("gaps", [])),
            papers=len(state.get("papers", [])),
        )
        return {
            "gaps": res.get("gaps", []),
            "matrix": res.get("matrix", []),
            "gap_coverage": res.get("coverage", {}),
            "warnings": list(state.get("warnings", [])) + res.get("warnings", []),
            "stage_log": _log(state, "gap_analysis", {"gaps": len(res.get("gaps", []))}),
        }

    async def node_deep_research(state: ResearchState) -> dict[str, Any]:
        await stage_start("deep_research", agent=ctx.deep.name)
        step = await rt.step(
            ctx.deep.name,
            "deep_research",
            lambda: ctx.deep.run(
                project_id=ctx.project_id,
                topic=state["topic"],
                papers=state.get("papers", []),
                gaps=state.get("gaps", []),
                matrix=state.get("matrix", []),
                domain=state.get("domain", "computer_science"),
            ),
        )
        res = step.value if step.ok else {"subquestions": [], "report_markdown": "", "warnings": [step.error or "deep research failed"]}
        await rt.update_run(stats={"deep_research": _slim_deep(res)})
        await stage_finish(
            "deep_research",
            "completed" if step.ok else "failed",
            error=None if step.ok else step.error,
            subquestions=len(res.get("subquestions", [])),
            extra_papers=res.get("extra_papers_found", 0),
        )
        return {
            "deep_research": _slim_deep(res),
            "warnings": list(state.get("warnings", [])) + res.get("warnings", []),
            "stage_log": _log(state, "deep_research", {"extra_papers": res.get("extra_papers_found", 0)}),
        }

    async def node_ideas(state: ResearchState) -> dict[str, Any]:
        await stage_start("ideas", agent="ResearchQuestionSkill")
        gaps = state.get("gaps", [])
        res = await ctx.rqs.run(
            {
                "topic": state["topic"],
                "domain": state.get("domain", "computer_science"),
                "gaps": [
                    {
                        "title": g["title"],
                        "description": g.get("description", ""),
                        "evidence_paper_ids": g.get("evidence_paper_ids", []),
                        "kind": g.get("kind", "hypothesis"),
                        "confidence": g.get("confidence", 0.0),
                    }
                    for g in gaps
                ],
                "max_ideas": 3,
            }
        )
        ideas = (res.data or {}).get("ideas", [])
        await _persist_ideas(ctx.project_id, ideas, res.generated_by)
        await stage_finish("ideas", "completed" if res.ok else "failed",
                           error=res.error, ideas=len(ideas), generated_by=res.generated_by)
        return {
            "ideas": ideas,
            "warnings": list(state.get("warnings", [])) + res.warnings,
            "stage_log": _log(state, "idea_generation", {"ideas": len(ideas), "by": res.generated_by}),
        }

    async def node_draft(state: ResearchState) -> dict[str, Any]:
        cfg = state.get("config") or {}
        if not cfg.get("generate_draft", True):
            await stage_skip("drafting", "drafting disabled in the run configuration")
            return {"stage_log": _log(state, "drafting", {"skipped": "user disabled drafting"})}
        await stage_start("drafting", agent=ctx.drafting.name)
        idea = (state.get("ideas") or [None])[0]
        step = await rt.step(
            ctx.drafting.name,
            "draft_manuscript",
            lambda: ctx.drafting.run(
                project_id=ctx.project_id,
                topic=state["topic"],
                papers=state.get("papers", []),
                gaps=state.get("gaps", []),
                idea=idea,
                domain=state.get("domain", "computer_science"),
                style=cfg.get("citation_style", "IEEE"),
                feedback=state.get("citation_feedback"),
                version_note=(
                    "Revision after citation audit" if state.get("citation_feedback") else None
                ),
            ),
        )
        res = step.value or {}
        await rt.update_run(stage="drafting")
        if not res.get("ok"):
            await stage_finish("drafting", "failed", error=res.get("error", "drafting failed"))
            return {
                "errors": list(state.get("errors", [])) + [res.get("error", "drafting failed")],
                "stage_log": _log(state, "drafting", {"error": res.get("error")}),
            }
        await stage_finish(
            "drafting",
            "completed",
            version=res["draft"]["version"],
            words=sum(
                (sec.get("word_count", 0) if isinstance(sec, dict) else 0)
                for sec in (res["draft"].get("sections") or [])
            ),
            references=len(res.get("bibliography", [])),
        )
        return {
            "draft": res["draft"],
            "bibliography": res["bibliography"],
            "warnings": list(state.get("warnings", [])) + res.get("warnings", []),
            "stage_log": _log(state, "drafting", {"version": res["draft"]["version"]}),
        }

    async def node_citation(state: ResearchState) -> dict[str, Any]:
        if not state.get("draft"):
            await stage_skip("citation_audit", "no draft was produced")
            return {"stage_log": _log(state, "citation_audit", {"skipped": "no draft"})}
        await stage_start("citation_audit", agent=ctx.citation.name)
        step = await rt.step(
            ctx.citation.name,
            "citation_audit",
            lambda: ctx.citation.run(
                project_id=ctx.project_id,
                draft=state["draft"],
                bibliography=state.get("bibliography", []),
            ),
        )
        if not step.ok:
            await stage_finish("citation_audit", "failed", error=step.error or "citation audit failed")
            return {
                "errors": list(state.get("errors", [])) + [step.error or "citation audit failed"],
                "stage_log": _log(state, "citation_audit", {"error": step.error}),
            }
        res = step.value
        report = res["report"]
        summary = report.get("summary", {})
        need_fix = summary.get("doi_failed", 0) > 0 or summary.get("missing_bibliography_entries")
        feedback = None
        if need_fix and state.get("draft_revisions", 0) < settings.max_graph_revisions:
            problems = []
            for e in report.get("entries", []):
                if e.get("issues"):
                    problems.append(f"{e['key']}: {'; '.join(e['issues'])}")
            if summary.get("missing_bibliography_entries"):
                problems.append(
                    f"in-text markers without bibliography entries: {summary['missing_bibliography_entries']}"
                )
            feedback = "; ".join(problems[:8])
        await rt.update_run(stage="citation_audit")
        await stage_finish(
            "citation_audit",
            "completed",
            references=summary.get("references", 0),
            doi_verified=summary.get("doi_verified", 0),
            doi_failed=summary.get("doi_failed", 0),
            doi_unavailable=summary.get("doi_unavailable", 0),
            revision_requested=bool(feedback),
        )
        return {
            "citation_report": report,
            "citation_feedback": feedback,
            "warnings": list(state.get("warnings", [])) + res.get("warnings", []),
            "stage_log": _log(state, "citation_audit", summary),
        }

    async def node_draft_revision(state: ResearchState) -> dict[str, Any]:
        return {
            "draft_revisions": int(state.get("draft_revisions", 0)) + 1,
            "stage_log": _log(state, "draft_revision", {"reason": "citation audit feedback"}),
        }

    async def node_radar(state: ResearchState) -> dict[str, Any]:
        cfg = state.get("config") or {}
        if not cfg.get("run_radar", True):
            await stage_skip("radar", "venues & funding disabled in the run configuration")
            return {"stage_log": _log(state, "radar", {"skipped": "disabled"})}
        await stage_start("radar", agent=ctx.radar.name)
        step = await rt.step(
            ctx.radar.name,
            "venue_and_funding_radar",
            lambda: ctx.radar.run(
                project_id=ctx.project_id,
                topic=state["topic"],
                papers=state.get("papers", []),
                domain=state.get("domain", "computer_science"),
            ),
        )
        res = step.value or {"journals": []}
        await stage_finish(
            "radar",
            "completed" if step.ok else "failed",
            error=None if step.ok else step.error,
            venues=len(res.get("journals", [])),
            funders=len(res.get("funders", []) or res.get("funders_in_literature", []) or []),
        )
        return {
            "radar": res,
            "stage_log": _log(state, "radar", {"venues": len(res.get("journals", []))}),
        }

    async def node_collaboration(state: ResearchState) -> dict[str, Any]:
        cfg = state.get("config") or {}
        if not cfg.get("run_collaboration", True):
            await stage_skip("collaboration", "collaborator search disabled in the run configuration")
            return {"stage_log": _log(state, "collaboration", {"skipped": "disabled"})}
        await stage_start("collaboration", agent=ctx.collab.name)
        step = await rt.step(
            ctx.collab.name,
            "collaborator_search",
            lambda: ctx.collab.run(project_id=ctx.project_id, topic=state["topic"]),
        )
        res = step.value or {"candidates": [], "warnings": [step.error or "collaborator search failed"]}
        await stage_finish(
            "collaboration",
            "completed" if step.ok else "failed",
            error=None if step.ok else step.error,
            candidates=len(res.get("candidates", [])),
        )
        return {
            "collaborators": res,
            "warnings": list(state.get("warnings", [])) + res.get("warnings", []),
            "stage_log": _log(state, "collaboration", {"candidates": len(res.get("candidates", []))}),
        }

    async def node_approval(state: ResearchState) -> dict[str, Any]:
        await stage_start("approval", gate="publication")
        need = settings.require_approval_before_export
        if not need:
            await stage_finish("approval", "completed", decision="not_required")
            return {
                "approval_status": "not_required",
                "export_ready": True,
                "stage_log": _log(state, "approval", {"status": "not_required"}),
            }
        draft = state.get("draft") or {}
        async with SessionLocal() as session:
            approval = Approval(
                project_id=ctx.project_id,
                run_id=ctx.run_id,
                artifact_type="draft",
                artifact_id=draft.get("id"),
                gate="publication",
                status="pending",
            )
            session.add(approval)
            await session.commit()
            approval_id = approval.id
        await rt.emit(
            "approval_requested",
            stage="approval",
            approval_id=approval_id,
            artifact="draft",
            draft_version=draft.get("version"),
        )
        await rt.audit(
            "approval_requested",
            {"approval_id": approval_id, "draft_id": draft.get("id"), "gate": "publication"},
        )
        await stage_finish(
            "approval",
            "completed",
            approval_id=approval_id,
            decision="pending",
            note="the run pauses here until a human approves the draft",
        )
        return {
            "approval_status": "pending",
            "export_ready": False,
            "stage_log": _log(state, "approval", {"status": "pending", "approval_id": approval_id}),
        }

    async def node_finalize(state: ResearchState) -> dict[str, Any]:
        await stage_start("finalize")
        status = "completed" if state.get("papers") else "partial"
        if state.get("errors"):
            status = "partial"
        await stage_finish("finalize", "completed", run_status=status)
        await rt.emit("run_finished", stage="finalize", status=status)
        return {
            "final_status": status,
            "export_ready": state.get("export_ready", False) or state.get("approval_status") == "not_required",
            "stage_log": _log(state, "finalize", {"status": status}),
        }

    async def node_no_evidence(state: ResearchState) -> dict[str, Any]:
        for key in ("merge_rank", "gap_analysis", "deep_research", "ideas", "drafting",
                    "citation_audit", "radar", "collaboration", "approval", "finalize"):
            await stage_skip(key, "no scholarly records were retrieved, so this stage never ran")
        await rt.emit(
            "run_failed",
            stage="discovery",
            status="failed",
            reason="no scholarly records could be retrieved from any source",
            failed_sources=state.get("failed_sources", []),
        )
        return {
            "errors": list(state.get("errors", []))
            + ["discovery returned zero records; the workflow stopped rather than inventing data"],
            "final_status": "failed",
            "stage_log": _log(state, "abort", {"reason": "no_evidence"}),
        }

    async def node_revise_search(state: ResearchState) -> dict[str, Any]:
        await rt.emit(
            "search_revised",
            stage="revising",
            reason="insufficient literature",
            have=len(state.get("papers", [])),
        )
        return {
            "discovery_revisions": int(state.get("discovery_revisions", 0)) + 1,
            "stage_log": _log(state, "revise_search", {"have": len(state.get("papers", []))}),
        }

    graph = StateGraph(ResearchState)
    def _cancellable(fn: Callable[[ResearchState], Any]) -> Callable[[ResearchState], Any]:
        async def wrapper(state: ResearchState) -> Any:
            # Cooperative cancellation: checked between nodes, so a cancelled run
            # cannot start another node.
            rt.check_cancelled()
            return await fn(state)

        return wrapper

    graph.add_node("discover", _cancellable(node_discover))
    graph.add_node("revise_search", _cancellable(node_revise_search))
    graph.add_node("no_evidence", _cancellable(node_no_evidence))
    graph.add_node("gap_analysis", _cancellable(node_gap))
    graph.add_node("deep_research", _cancellable(node_deep_research))
    graph.add_node("ideas", _cancellable(node_ideas))
    graph.add_node("drafting", _cancellable(node_draft))
    graph.add_node("citation_audit", _cancellable(node_citation))
    graph.add_node("draft_revision", _cancellable(node_draft_revision))
    graph.add_node("radar", _cancellable(node_radar))
    graph.add_node("collaboration", _cancellable(node_collaboration))
    graph.add_node("approval", _cancellable(node_approval))
    graph.add_node("finalize", _cancellable(node_finalize))

    graph.set_entry_point("discover")
    graph.add_conditional_edges(
        "discover",
        lambda s: route_after_discovery(s),
        {"gap": "gap_analysis", "revise": "revise_search", "stop": "no_evidence"},
    )
    graph.add_edge("revise_search", "discover")
    graph.add_edge("gap_analysis", "deep_research")
    graph.add_edge("deep_research", "ideas")
    graph.add_edge("ideas", "drafting")
    graph.add_edge("drafting", "citation_audit")
    graph.add_conditional_edges(
        "citation_audit",
        lambda s: route_after_citation(s),
        {"revise_draft": "draft_revision", "continue": "radar"},
    )
    graph.add_edge("draft_revision", "drafting")
    graph.add_edge("radar", "collaboration")
    graph.add_edge("collaboration", "approval")
    graph.add_edge("approval", "finalize")
    graph.add_edge("finalize", END)
    graph.add_edge("no_evidence", END)

    return graph.compile()


def route_after_discovery(state: ResearchState) -> str:
    papers = state.get("papers", [])
    cfg = state.get("config") or {}
    min_papers = int(cfg.get("min_papers", settings.min_papers_for_analysis))
    revisions = int(state.get("discovery_revisions", 0))
    if not papers:
        return "stop"
    if len(papers) < min_papers and revisions < settings.max_graph_revisions:
        return "revise"
    return "gap"


def route_after_citation(state: ResearchState) -> str:
    feedback = state.get("citation_feedback")
    if feedback and int(state.get("draft_revisions", 0)) < settings.max_graph_revisions:
        return "revise_draft"
    return "continue"


def _log(state: ResearchState, stage: str, detail: dict[str, Any]) -> list[dict[str, Any]]:
    return list(state.get("stage_log", [])) + [
        {"stage": stage, "detail": detail, "ts": time.strftime("%H:%M:%S")}
    ]


def _slim_deep(res: dict[str, Any]) -> dict[str, Any]:
    """Keep the persisted copy small enough for JSON columns."""
    return {
        "subquestions": res.get("subquestions", []),
        "extra_papers_found": res.get("extra_papers_found", 0),
        "extra_papers": res.get("extra_papers", []),
        "patterns": res.get("patterns", []),
        "uncertainties": res.get("uncertainties", []),
        "report_markdown": (res.get("report_markdown") or "")[:20000],
        "generated_by": res.get("generated_by"),
        "warnings": res.get("warnings", []),
        "evidence_papers": res.get("evidence_papers", 0),
    }


async def _persist_ideas(project_id: str, ideas: list[dict[str, Any]], generated_by: str) -> None:
    from sqlalchemy import delete

    from app.db.models import ResearchIdea

    async with SessionLocal() as session:
        await session.execute(delete(ResearchIdea).where(ResearchIdea.project_id == project_id))
        for idea in ideas:
            session.add(
                ResearchIdea(
                    project_id=project_id,
                    title=idea.get("title", "")[:500],
                    research_questions=idea.get("research_questions", []),
                    objectives=idea.get("objectives", []),
                    proposed_methodology=idea.get("proposed_methodology", ""),
                    suggested_datasets=idea.get("suggested_datasets", []),
                    metrics=idea.get("metrics", []),
                    challenges=idea.get("challenges", []),
                    feasibility=idea.get("feasibility", ""),
                    generated_by=generated_by,
                )
            )
        await session.commit()
