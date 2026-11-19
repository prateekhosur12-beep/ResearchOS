"""Workflow stage tracking (Lab 6 + Lab 7 observability).

Twelve named stages, each with a real status derived from what the backend actually
did — never a simulated percentage:

    pending → running → completed | failed | cancelled | skipped

State is written to ``workflow_runs.stats_json["stages"]`` on every transition and
published on the SSE stream as a ``stage`` event, so a browser that connects late
still reconstructs the same picture (the event bus buffers per run).
"""

from __future__ import annotations

import time
from typing import Any

from app.logging_conf import get_logger

log = get_logger("stages")

#: (key, display name, short description) — the order is the order on screen.
STAGE_DEFS: list[tuple[str, str, str]] = [
    ("understand_topic", "Understand Topic", "Sanitise the title, plan search queries"),
    ("search_sources", "Search Sources", "OpenAlex + Crossref + arXiv over MCP"),
    ("merge_rank", "Merge and Rank", "Deduplicate, score and store records"),
    ("gap_analysis", "Analyse Gaps", "Evidence matrix → gaps with quoted support"),
    ("deep_research", "Deep Research", "Sub-questions, extra retrieval, synthesis"),
    ("ideas", "Generate Ideas", "Research questions, method, metrics"),
    ("drafting", "Draft Manuscript", "Section-by-section proposal draft"),
    ("citation_audit", "Audit Citations", "Resolve DOIs, check markers vs bibliography"),
    ("radar", "Venues and Funding", "Venue metadata, funders, collaborators"),
    ("collaboration", "Collaborators", "Author overlap in the retrieved corpus"),
    ("approval", "Human Approval", "Publication gate — human decision required"),
    ("finalize", "Finalise", "Persist status, audit entry, emit run_finished"),
]

STAGE_KEYS = [k for k, _, _ in STAGE_DEFS]
STAGE_NAMES = {k: n for k, n, _ in STAGE_DEFS}
TERMINAL = {"completed", "failed", "cancelled", "skipped"}


def _blank() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": name,
            "description": desc,
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "attempts": 0,
            "tool_calls": 0,
            "llm_calls": 0,
            "detail": {},
            "error": None,
        }
        for key, name, desc in STAGE_DEFS
    ]


class StageTracker:
    """Owns the 12-stage state machine for one run."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.stages = _blank()
        self._index = {s["key"]: s for s in self.stages}
        self._started_at: dict[str, float] = {}
        self._tool_base = 0
        self._llm_base = 0

    # ------------------------------------------------------------------ helpers
    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self.stages]

    def current(self) -> str | None:
        for s in self.stages:
            if s["status"] == "running":
                return s["key"]
        return None

    def _touch(self) -> None:
        self.stages.sort(key=lambda s: STAGE_KEYS.index(s["key"]))

    async def _publish(self, event: str, stage: dict[str, Any]) -> None:
        try:
            await self.runtime.update_run(stats={"stages": self.snapshot()})
        except Exception as exc:  # noqa: BLE001 - progress must never kill a run
            log.warning("stage persist failed: %s", exc)
        try:
            await self.runtime.emit(
                "stage",
                stage=stage["key"],
                stage_name=stage["name"],
                status=stage["status"],
                duration_ms=stage["duration_ms"],
                detail=stage["detail"],
                error=stage["error"],
                event=event,
                stages=self.snapshot(),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("stage emit failed: %s", exc)

    def _counters(self) -> dict[str, int]:
        stats = getattr(self.runtime, "stats", None)
        if stats is None:
            return {"tool_calls": 0, "llm_calls": 0}
        return {
            "tool_calls": max(0, int(getattr(stats, "tool_calls", 0)) - self._tool_base),
            "llm_calls": max(0, int(getattr(stats, "llm_calls", 0)) - self._llm_base),
        }

    # ------------------------------------------------------------------- states
    async def start(self, key: str, **detail: Any) -> None:
        stage = self._index.get(key)
        if stage is None:
            return
        if stage["status"] == "running":
            stage["detail"].update(detail)
            await self._publish("updated", stage)
            return
        prev_c = self._counters()
        self._tool_base = int(getattr(getattr(self.runtime, "stats", None), "tool_calls", 0)) 
        self._llm_base = int(getattr(getattr(self.runtime, "stats", None), "llm_calls", 0))
        stage.update(
            {
                "status": "running",
                "started_at": _now(),
                "finished_at": None,
                "duration_ms": None,
                "attempts": stage["attempts"] + 1,
                "detail": {**stage["detail"], **detail},
                "error": None,
            }
        )
        self._started_at[key] = time.perf_counter()
        await self.runtime.update_run(stage=key)
        await self._publish("started", stage)
        log.info("stage start key=%s prev_tool_calls=%s", key, prev_c["tool_calls"])

    async def finish(self, key: str, status: str = "completed", *, error: str | None = None, **detail: Any) -> None:
        stage = self._index.get(key)
        if stage is None:
            return
        started = self._started_at.pop(key, None)
        duration = int((time.perf_counter() - started) * 1000) if started else stage["duration_ms"]
        counters = self._counters()
        stage.update(
            {
                "status": status,
                "finished_at": _now(),
                "duration_ms": duration,
                "detail": {**stage["detail"], **detail},
                "tool_calls": stage["tool_calls"] + counters["tool_calls"],
                "llm_calls": stage["llm_calls"] + counters["llm_calls"],
                "error": error,
            }
        )
        self._tool_base = int(getattr(getattr(self.runtime, "stats", None), "tool_calls", 0))
        self._llm_base = int(getattr(getattr(self.runtime, "stats", None), "llm_calls", 0))
        await self._publish(status, stage)

    async def fail(self, key: str, error: str, **detail: Any) -> None:
        await self.finish(key, "failed", error=error, **detail)

    async def skip(self, key: str, reason: str) -> None:
        stage = self._index.get(key)
        if stage is None or stage["status"] in TERMINAL:
            return
        stage.update(
            {
                "status": "skipped",
                "started_at": stage["started_at"] or _now(),
                "finished_at": _now(),
                "duration_ms": 0,
                "detail": {**stage["detail"], "skip_reason": reason},
            }
        )
        await self._publish("skipped", stage)

    async def cancelled(self) -> None:
        """Mark whatever was running as cancelled; leave the rest pending."""
        changed = False
        for stage in self.stages:
            if stage["status"] == "running":
                started = self._started_at.pop(stage["key"], None)
                stage.update(
                    {
                        "status": "cancelled",
                        "finished_at": _now(),
                        "duration_ms": int((time.perf_counter() - started) * 1000) if started else None,
                        "error": "cancelled by user",
                    }
                )
                changed = True
        if changed:
            await self._publish("cancelled", {"key": "run", "name": "run", "status": "cancelled",
                                             "duration_ms": None, "detail": {}, "error": None})
        else:
            await self.runtime.update_run(stats={"stages": self.snapshot()})

    async def fail_running(self, error: str) -> None:
        for stage in self.stages:
            if stage["status"] == "running":
                await self.fail(stage["key"], error)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def stages_from_stats(stats: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return the persisted stage list, filling in blanks for older runs."""
    stored = (stats or {}).get("stages")
    if not isinstance(stored, list) or not stored:
        return _blank()
    known = {s.get("key") for s in stored if isinstance(s, dict)}
    out = [s for s in stored if isinstance(s, dict) and s.get("key") in STAGE_KEYS]
    for key, name, desc in STAGE_DEFS:
        if key not in known:
            out.append(
                {
                    "key": key,
                    "name": name,
                    "description": desc,
                    "status": "pending",
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": None,
                    "attempts": 0,
                    "tool_calls": 0,
                    "llm_calls": 0,
                    "detail": {},
                    "error": None,
                }
            )
    out.sort(key=lambda s: STAGE_KEYS.index(s["key"]))
    return out
