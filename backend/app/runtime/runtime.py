"""Agent runtime: state, timing, retries, cancellation, trace + audit (Lab 6 / 12).

Every agent action goes through `AgentRuntime.step`. The runtime records what
actually happened — including failures — and never upgrades a failed step to
"success". The audit chain is a hash chain over (prev_hash, action, payload), so
tampering is detectable by `verify_audit_chain`; the store itself is ordinary
writable SQLite and is described as tamper-evident, not immutable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select

from app.db.base import SessionLocal
from app.db.models import AuditRecord, TraceEvent, WorkflowRun
from app.events import EventBus, bus as global_bus
from app.logging_conf import get_logger, run_id_ctx

log = get_logger("runtime")


class RunCancelled(RuntimeError):
    pass


@dataclass
class StepResult:
    ok: bool
    value: Any = None
    error: str | None = None
    duration_ms: int = 0
    attempts: int = 1


@dataclass
class RuntimeStats:
    steps: int = 0
    failed_steps: int = 0
    retries: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    started_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "failed_steps": self.failed_steps,
            "retries": self.retries,
            "tool_calls": self.tool_calls,
            "llm_calls": self.llm_calls,
            "elapsed_s": round(time.time() - self.started_at, 2),
        }


class AgentRuntime:
    def __init__(
        self,
        run_id: str,
        project_id: str,
        event_bus: EventBus | None = None,
        max_retries: int = 1,
    ) -> None:
        self.run_id = run_id
        self.project_id = project_id
        self.bus = event_bus or global_bus
        self.max_retries = max_retries
        self.stats = RuntimeStats()
        self._seq = 0
        self._cancel = asyncio.Event()
        self._cancel_reason = "cancelled by user"
        self.llm_available: bool | None = None
        run_id_ctx.set(run_id)

    # ------------------------------------------------------------------ control
    def cancel(self, reason: str = "cancelled by user") -> None:
        """Request cooperative cancellation. Idempotent."""
        if not self._cancel.is_set():
            self._cancel_reason = reason or "cancelled by user"
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def cancel_reason(self) -> str:
        return self._cancel_reason

    def check_cancelled(self) -> None:
        """Raise ``RunCancelled`` if cancellation has been requested.

        Called between workflow nodes, between search attempts and between source
        dispatches, so a cancelled run stops doing work instead of finishing it.
        """
        if self._cancel.is_set():
            raise RunCancelled(self._cancel_reason)

    # Backwards-compatible alias (older call sites used the private name).
    def _check_cancel(self) -> None:
        self.check_cancelled()

    # ------------------------------------------------------------------ events
    async def emit(self, event_type: str, **payload: Any) -> None:
        await self.bus.publish(self.run_id, {"type": event_type, "run_id": self.run_id, **payload})

    async def progress(self, stage: str, message: str, **payload: Any) -> None:
        await self.emit("progress", stage=stage, message=message, **payload)

    # -------------------------------------------------------------------- steps
    async def step(
        self,
        agent: str,
        name: str,
        fn: Callable[[], Awaitable[Any]],
        *,
        retries: int | None = None,
        detail: dict[str, Any] | None = None,
    ) -> StepResult:
        self._check_cancel()
        attempts_allowed = (self.max_retries if retries is None else retries) + 1
        last_error: str | None = None
        started = time.perf_counter()

        for attempt in range(1, attempts_allowed + 1):
            attempt_started = time.perf_counter()
            await self.emit(
                "step_started",
                agent=agent,
                step=name,
                attempt=attempt,
                detail=detail or {},
            )
            try:
                value = await fn()
                duration = int((time.perf_counter() - attempt_started) * 1000)
                self.stats.steps += 1
                await self._trace(agent, name, "ok", duration, detail, attempt)
                await self.emit("step_finished", agent=agent, step=name, status="ok", duration_ms=duration)
                return StepResult(ok=True, value=value, duration_ms=int((time.perf_counter() - started) * 1000), attempts=attempt)
            except RunCancelled:
                await self._trace(agent, name, "cancelled", int((time.perf_counter() - attempt_started) * 1000), detail, attempt)
                await self.emit("step_finished", agent=agent, step=name, status="cancelled")
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = f"{exc.__class__.__name__}: {exc}"
                duration = int((time.perf_counter() - attempt_started) * 1000)
                self.stats.failed_steps += 1
                await self._trace(agent, name, "error", duration, {**(detail or {}), "error": last_error}, attempt)
                await self.emit(
                    "step_finished", agent=agent, step=name, status="error",
                    duration_ms=duration, error=last_error,
                )
                log.warning("step failed agent=%s step=%s attempt=%s err=%s", agent, name, attempt, last_error)
                if attempt < attempts_allowed:
                    self.stats.retries += 1
                    await asyncio.sleep(min(0.5 * attempt, 2.0))
                    continue
        return StepResult(ok=False, error=last_error, duration_ms=int((time.perf_counter() - started) * 1000), attempts=attempts_allowed)

    async def _trace(
        self,
        agent: str,
        step: str,
        status: str,
        duration_ms: int,
        detail: dict[str, Any] | None,
        attempt: int,
    ) -> None:
        self._seq += 1
        try:
            async with SessionLocal() as session:
                session.add(
                    TraceEvent(
                        project_id=self.project_id,
                        run_id=self.run_id,
                        seq=self._seq,
                        agent=agent,
                        step=step,
                        status=status,
                        duration_ms=duration_ms,
                        detail_json={**(detail or {}), "attempt": attempt},
                    )
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("trace write failed: %s", exc)

    # -------------------------------------------------------------- audit chain
    async def audit(self, action: str, payload: dict[str, Any], actor: str = "system") -> None:
        try:
            async with SessionLocal() as session:
                last = (
                    await session.execute(
                        select(AuditRecord)
                        .where(AuditRecord.project_id == self.project_id)
                        .order_by(AuditRecord.seq.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                prev_hash = last.hash if last else ""
                seq = (last.seq + 1) if last else 1
                body = json.dumps(
                    {"seq": seq, "action": action, "actor": actor, "payload": payload},
                    sort_keys=True,
                    default=str,
                )
                digest = hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()
                session.add(
                    AuditRecord(
                        project_id=self.project_id,
                        seq=seq,
                        action=action,
                        actor=actor,
                        payload_json=payload,
                        prev_hash=prev_hash,
                        hash=digest,
                    )
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("audit write failed: %s", exc)

    # ------------------------------------------------------------------ run meta
    async def update_run(self, *, stats: dict[str, Any] | None = None, **fields: Any) -> None:
        try:
            async with SessionLocal() as session:
                run = await session.get(WorkflowRun, self.run_id)
                if run is None:
                    return
                for k, v in fields.items():
                    if hasattr(run, k):
                        setattr(run, k, v)
                merged = {**(run.stats_json or {}), "runtime": self.stats.as_dict()}
                if stats:
                    merged.update(stats)
                run.stats_json = merged
                await session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("run update failed: %s", exc)


async def verify_audit_chain(project_id: str) -> dict[str, Any]:
    """Re-compute the hash chain and report the first broken link, if any."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(AuditRecord)
                .where(AuditRecord.project_id == project_id)
                .order_by(AuditRecord.seq.asc())
            )
        ).scalars().all()
    prev = ""
    for row in rows:
        body = json.dumps(
            {"seq": row.seq, "action": row.action, "actor": row.actor, "payload": row.payload_json},
            sort_keys=True,
            default=str,
        )
        expected = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
        if row.prev_hash != prev or row.hash != expected:
            return {
                "valid": False,
                "records": len(rows),
                "broken_at_seq": row.seq,
                "detail": "hash chain mismatch — records were modified, reordered or removed",
            }
        prev = row.hash
    return {"valid": True, "records": len(rows), "broken_at_seq": None, "detail": "chain intact"}
