"""Run service: owns run lifecycle, background execution and cancellation.

One run = one project topic execution. Run state is persisted at every node, and
the WebSocket/SSE stream is fed from the same runtime that writes the trace, so the
UI cannot show progress that did not happen.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import time
from contextlib import AsyncExitStack
from typing import Any

from sqlalchemy import func, select

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Paper, Project, WorkflowRun
from app.events import bus
from app.graph.workflow import WorkflowContext, build_graph
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime, RunCancelled
from app.services.stages import StageTracker, stages_from_stats
from app.tools.runner import ToolRunner

log = get_logger("workflow")


ACTIVE_STATUSES = {"pending", "running", "cancelling"}


class RunConflict(RuntimeError):
    """Raised when a project already has an active run."""

    def __init__(self, run_id: str, status: str) -> None:
        super().__init__(
            f"a run is already {status} for this project ({run_id}); cancel it before starting another"
        )
        self.run_id = run_id
        self.status = status


class WorkflowService:
    def __init__(self) -> None:
        self._runtimes: dict[str, AgentRuntime] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._stages: dict[str, StageTracker] = {}
        self._cancel_reasons: dict[str, str] = {}

    # ------------------------------------------------------------------ create
    async def create_run(
        self, project_id: str, topic: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        async with SessionLocal() as session:
            project = await session.get(Project, project_id)
            if project is None:
                raise ValueError("project not found")

            # One live run per project: two concurrent runs would interleave writes
            # into the same project rows. The client is told exactly what to cancel.
            active = (
                await session.execute(
                    select(WorkflowRun)
                    .where(
                        WorkflowRun.project_id == project_id,
                        WorkflowRun.status.in_(tuple(ACTIVE_STATUSES)),
                    )
                    .order_by(WorkflowRun.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if active is not None and self.is_active(active.id):
                raise RunConflict(active.id, active.status)

            # Carry the brief and questions into the run: agents get them, search
            # tools never do (see app/services/query_planner.py).
            config = {
                **config,
                "research_instructions": project.research_instructions or "",
                "research_questions": list(project.research_questions or []),
                "domain": project.domain,
            }
            run = WorkflowRun(
                project_id=project_id,
                topic=topic,
                status="pending",
                stage="created",
                config_json=config,
                stats_json={},
            )
            session.add(run)
            await session.commit()
            return {"id": run.id, "project_id": project_id, "topic": topic, "status": "pending"}

    def start(
        self, run_id: str, project_id: str, topic: str, config: dict[str, Any], domain: str
    ) -> None:
        task = asyncio.create_task(
            self._execute(run_id, project_id, topic, config, domain), name=f"run-{run_id}"
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(run_id, None))

    async def request_cancel(self, run_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
        """Cooperative cancellation with an escalation deadline.

        1. flip the runtime's cancel token (nodes, search attempts and source
           dispatches check it and raise ``RunCancelled``);
        2. wait up to ``settings.cancel_grace_seconds`` for the graph to unwind;
        3. if it is still alive, cancel the asyncio task, which aborts in-flight
           HTTP requests;
        4. the run is persisted as ``cancelled`` — never as failed or completed.
        """
        self._cancel_reasons[run_id] = reason
        runtime = self._runtimes.get(run_id)
        task = self._tasks.get(run_id)

        async with SessionLocal() as session:
            run = await session.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError("run not found")
            status = run.status
            if status in ("cancelled",):
                return {"requested": False, "cancelled": True, "status": "cancelled",
                        "detail": "run already cancelled"}
            if status not in ACTIVE_STATUSES or task is None or task.done():
                return {
                    "requested": False,
                    "cancelled": False,
                    "status": status,
                    "detail": f"run is not executing (status={status}); nothing to cancel",
                }
            run.status = "cancelling"
            await session.commit()

        if runtime is not None:
            runtime.cancel(reason)
            try:
                await runtime.emit("cancel_requested", stage=runtime.stats and "cancelling",
                                   reason=reason, status="cancelling")
            except Exception:  # noqa: BLE001
                pass

        if task is not None:
            grace = max(0.0, float(settings.cancel_grace_seconds))
            done, _ = await asyncio.wait({task}, timeout=grace)
            if not done:
                log.info("cancel escalation: forcing task cancellation run=%s", run_id)
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        async with SessionLocal() as session:
            run = await session.get(WorkflowRun, run_id)
            final = run.status if run else "cancelled"
        return {
            "requested": True,
            "cancelled": final == "cancelled",
            "status": final,
            "detail": "cancellation processed" if final == "cancelled"
            else f"run finished as {final} before cancellation took effect",
        }

    def cancel(self, run_id: str) -> bool:
        """Synchronous token flip (kept for internal callers and tests)."""
        runtime = self._runtimes.get(run_id)
        if runtime:
            runtime.cancel(self._cancel_reasons.get(run_id, "cancelled by user"))
            return True
        return False

    def is_active(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return bool(task and not task.done())

    # ----------------------------------------------------------------- execute
    async def _execute(
        self,
        run_id: str,
        project_id: str,
        topic: str,
        config: dict[str, Any],
        domain: str,
    ) -> None:
        runtime = AgentRuntime(run_id=run_id, project_id=project_id)
        if run_id in self._cancel_reasons:
            runtime.cancel(self._cancel_reasons[run_id])
        self._runtimes[run_id] = runtime
        tracker = StageTracker(runtime)
        self._stages[run_id] = tracker
        await runtime.update_run(stats={"stages": tracker.snapshot()})
        started = time.perf_counter()
        tools = ToolRunner(project_id=project_id, run_id=run_id)

        await runtime.update_run(status="running", stage="starting")
        await runtime.emit("run_started", stage="starting", topic=topic, project_id=project_id)

        try:
            async with AsyncExitStack() as stack:
                await tools.start()
                stack.push_async_callback(tools.aclose)
                await runtime.emit(
                    "transport_ready",
                    stage="starting",
                    transport=tools.mode,
                    note=tools.transport_note,
                )
                await runtime.audit(
                    "run_started",
                    {"topic": topic, "config": config, "tool_transport": tools.mode},
                )

                ctx = WorkflowContext(runtime, tools, project_id, run_id, stages=tracker)
                graph = build_graph(ctx)
                initial = {
                    "project_id": project_id,
                    "run_id": run_id,
                    "topic": topic,
                    "domain": domain,
                    "config": config,
                    "papers": [],
                    "gaps": [],
                    "warnings": [],
                    "errors": [],
                    "stage_log": [],
                    "discovery_revisions": 0,
                    "draft_revisions": 0,
                }
                final_state = await graph.ainvoke(
                    initial, config={"recursion_limit": 40}
                )

                status = final_state.get("final_status") or "completed"
                if final_state.get("approval_status") == "pending":
                    status = "awaiting_approval"
                if final_state.get("errors"):
                    status = "partial" if final_state.get("papers") else "failed"

                async with SessionLocal() as session:
                    paper_count = (
                        await session.execute(
                            select(func.count(Paper.id)).where(Paper.project_id == project_id)
                        )
                    ).scalar_one()

                summary = {
                    "papers": len(final_state.get("papers", [])),
                    "papers_in_project": paper_count,
                    "gaps": len(final_state.get("gaps", [])),
                    "ideas": len(final_state.get("ideas", [])),
                    "draft_version": (final_state.get("draft") or {}).get("version"),
                    "queries": final_state.get("queries", []),
                    "failed_sources": final_state.get("failed_sources", []),
                    "discovery": final_state.get("discovery_stats", {}),
                    "gap_coverage": final_state.get("gap_coverage", {}),
                    "citation_summary": (final_state.get("citation_report") or {}).get("summary", {}),
                    "models": {
                        "llm_available": bool(final_state.get("discovery_stats", {}).get("llm_available")),
                        "llm_detail": final_state.get("discovery_stats", {}).get("llm_detail", ""),
                        "tool_transport": tools.mode,
                        "tool_transport_note": tools.transport_note,
                    },
                    "warnings": list(dict.fromkeys(final_state.get("warnings", []))),
                    "errors": list(dict.fromkeys(final_state.get("errors", []))),
                    "approval_status": final_state.get("approval_status", "not_requested"),
                    "stage_log": final_state.get("stage_log", []),
                    "elapsed_s": round(time.perf_counter() - started, 2),
                }
                await runtime.update_run(
                    status=status,
                    stage=final_state.get("stage_log", [{}])[-1].get("stage", "finalize")
                    if final_state.get("stage_log")
                    else "finalize",
                    finished_at=dt.datetime.now(dt.timezone.utc),
                    stats=summary,
                )
                await runtime.audit(
                    "run_finished",
                    {"status": status, "papers": summary["papers"], "gaps": summary["gaps"]},
                )
                if status not in ("failed",):
                    await runtime.emit("run_finished", stage="finalize", status=status, summary=summary)

        except (RunCancelled, asyncio.CancelledError):
            reason = self._cancel_reasons.get(run_id, "cancelled by user")
            await tracker.cancelled()
            async with SessionLocal() as session:
                run = await session.get(WorkflowRun, run_id)
                previous = dict((run.stats_json or {}) if run else {})
            await runtime.update_run(
                status="cancelled",
                stage="cancelled",
                error=f"cancelled: {reason}",
                finished_at=dt.datetime.now(dt.timezone.utc),
                stats={
                    "cancelled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "cancel_reason": reason,
                    "elapsed_s": round(time.perf_counter() - started, 2),
                    "pending_artifacts": _pending_artifacts(previous),
                },
            )
            await runtime.audit(
                "run_cancelled",
                {
                    "topic": topic,
                    "reason": reason,
                    "cancelled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "stage": previous.get("stage") or tracker.current(),
                },
            )
            await runtime.emit(
                "run_cancelled", stage="cancelled", status="cancelled", reason=reason
            )
            log.info("run cancelled id=%s reason=%s", run_id, reason)
        except Exception as exc:  # noqa: BLE001
            log.exception("run failed id=%s", run_id)
            await tracker.fail_running(f"{exc.__class__.__name__}: {exc}")
            await runtime.update_run(
                status="failed",
                stage="error",
                error=f"{exc.__class__.__name__}: {exc}",
                finished_at=dt.datetime.now(dt.timezone.utc),
            )
            await runtime.audit("run_failed", {"error": str(exc)[:500]})
            await runtime.emit(
                "run_failed", stage="error", status="failed", error=f"{exc.__class__.__name__}: {exc}"
            )
        finally:
            self._runtimes.pop(run_id, None)
            self._stages.pop(run_id, None)
            self._cancel_reasons.pop(run_id, None)

    # ------------------------------------------------------------------ status
    async def run_status(self, run_id: str) -> dict[str, Any]:
        async with SessionLocal() as session:
            run = await session.get(WorkflowRun, run_id)
            if run is None:
                raise ValueError("run not found")
            return {
                "id": run.id,
                "project_id": run.project_id,
                "topic": run.topic,
                "status": run.status,
                "stage": run.stage,
                "llm_available": run.llm_available,
                "stats": run.stats_json or {},
                "error": run.error,
                "created_at": run.created_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "active": self.is_active(run_id),
                "stages": stages_from_stats(run.stats_json),
                "config": run.config_json or {},
            }


workflow_service = WorkflowService()
__all__ = ["WorkflowService", "workflow_service", "bus"]


def _pending_artifacts(stats: dict[str, Any]) -> list[str]:
    """What the cancelled run did *not* produce — reported, never simulated."""
    missing: list[str] = []
    if not stats.get("papers"):
        missing.append("papers")
    if not stats.get("gaps"):
        missing.append("gaps")
    if not stats.get("ideas"):
        missing.append("ideas")
    if not stats.get("draft_version"):
        missing.append("draft")
    if not stats.get("citation_summary"):
        missing.append("citation_audit")
    return missing


async def reconcile_stale_runs() -> int:
    """Runs left in ``running`` by a process restart can never finish.

    They are marked failed with an explicit reason rather than silently staying
    "running" forever (which would also block new runs on that project).
    """
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(WorkflowRun).where(WorkflowRun.status.in_(("pending", "running", "cancelling")))
            )
        ).scalars().all()
        for run in rows:
            if workflow_service.is_active(run.id):
                continue
            run.status = "failed"
            run.stage = "interrupted"
            run.error = "interrupted by server restart — this run never finished; start a new one"
            run.finished_at = dt.datetime.now(dt.timezone.utc)
        await session.commit()
        return len(rows)
