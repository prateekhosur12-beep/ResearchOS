"""Parallel multi-source search with partial-failure tolerance (Lab 8).

Independent source searches run concurrently, each with its own timeout. A failing
source never discards the results of a healthy one. The caller injects the tool
execution function, so the very same code path works whether tools are executed
through the MCP server or the direct registry.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.logging_conf import get_logger
from app.services.scholarly.records import ScholarlyRecord

log = get_logger("scholarly.aggregator")

SOURCES = ("openalex", "crossref", "arxiv")

ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass
class SourceReport:
    source: str
    status: str = "pending"  # ok | empty | error | timeout
    latency_ms: int = 0
    records: int = 0
    attempts: int = 1
    http_status: int | None = None
    error: str | None = None
    retrieved_at: str | None = None
    query: str = ""
    execution_mode: str = "direct"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "records": self.records,
            "attempts": self.attempts,
            "http_status": self.http_status,
            "error": self.error,
            "retrieved_at": self.retrieved_at,
            "query": self.query,
            "execution_mode": self.execution_mode,
        }


#: Source outcomes that count as "this source gave us nothing usable".
_FAILED = ("error", "timeout", "rate_limited")


@dataclass
class SearchBundle:
    records: list[ScholarlyRecord] = field(default_factory=list)
    reports: list[SourceReport] = field(default_factory=list)
    wall_ms: int = 0
    mode: str = "parallel"
    per_source: dict[str, list[ScholarlyRecord]] = field(default_factory=dict)

    @property
    def any_success(self) -> bool:
        return any(r.status in ("ok", "empty") for r in self.reports) if self.reports else False

    @property
    def all_failed(self) -> bool:
        if not self.reports:
            return True
        return all(r.status in _FAILED for r in self.reports)

    @property
    def failed_sources(self) -> list[str]:
        """Sources that did not answer — including ones we had to skip (rate limits)."""
        return [r.source for r in self.reports if r.status in _FAILED]

    def summary(self) -> dict[str, Any]:
        return {
            "sources": [r.as_dict() for r in self.reports],
            "records": len(self.records),
            "wall_ms": self.wall_ms,
            "mode": self.mode,
            "failed_sources": self.failed_sources,
        }


def record_from_dict(d: dict[str, Any]) -> ScholarlyRecord:
    return ScholarlyRecord(
        source=d.get("source", "unknown"),
        title=d.get("title", ""),
        source_query=d.get("source_query", ""),
        doi=d.get("doi"),
        arxiv_id=d.get("arxiv_id"),
        authors=d.get("authors") or [],
        year=d.get("year"),
        venue=d.get("venue"),
        abstract=d.get("abstract"),
        url=d.get("url"),
        pdf_url=d.get("pdf_url"),
        cited_by=d.get("cited_by"),
        type=d.get("type"),
        open_access=d.get("open_access"),
        raw=d.get("raw") or {},
        warnings=d.get("warnings") or [],
    )


def _caller_mode(caller: ToolCaller) -> str:
    """Resolve the real transport for a caller, including a bound method.

    ``ToolRunner.call`` is passed as ``runner.call``, so the bound instance holds
    the transport (mcp | direct) rather than the method object.
    """
    mode = getattr(caller, "mode", None)
    if not mode:
        mode = getattr(getattr(caller, "__self__", None), "mode", None)
    return str(mode) if mode else "direct"


async def _run_one(
    source: str,
    query: str,
    limit: int,
    year_from: int | None,
    year_to: int | None,
    types: list[str] | None,
    caller: ToolCaller,
    timeout: float,
) -> tuple[str, list[ScholarlyRecord], SourceReport]:
    report = SourceReport(source=source, query=query, execution_mode=_caller_mode(caller))
    started = time.perf_counter()
    try:
        payload = await asyncio.wait_for(
            caller(
                f"search_{source}",
                {
                    "query": query,
                    "limit": limit,
                    "year_from": year_from,
                    "year_to": year_to,
                    "types": types or [],
                },
            ),
            timeout=timeout,
        )
    except asyncio.CancelledError:
        # Cancellation is not a source failure: let it unwind the run.
        raise
    except asyncio.TimeoutError:
        report.status = "timeout"
        report.latency_ms = int((time.perf_counter() - started) * 1000)
        report.error = f"{source} search exceeded {timeout:.0f}s"
        report.retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        log.warning("source timeout source=%s query=%r", source, query)
        return source, [], report
    except Exception as exc:  # noqa: BLE001 - any tool failure degrades gracefully
        if exc.__class__.__name__ in {"RunCancelled", "CancelledError"}:
            # A cancelled run must stop here instead of being recorded as a failed source.
            raise
        report.status = "error"
        report.latency_ms = int((time.perf_counter() - started) * 1000)
        report.error = f"{exc.__class__.__name__}: {exc}"
        report.retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        log.warning("source error source=%s err=%s", source, report.error)
        return source, [], report

    if not isinstance(payload, dict):
        report.status = "error"
        report.error = f"unexpected tool payload type {type(payload).__name__}"
        report.latency_ms = int((time.perf_counter() - started) * 1000)
        return source, [], report

    report.status = str(payload.get("status") or "error")
    report.latency_ms = int(payload.get("latency_ms") or (time.perf_counter() - started) * 1000)
    report.attempts = int(payload.get("attempts") or 1)
    report.http_status = payload.get("http_status")
    report.error = payload.get("error")
    report.retrieved_at = payload.get("retrieved_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report.query = payload.get("query") or query
    records = [record_from_dict(r) for r in payload.get("records") or []]
    report.records = len(records)
    if report.status == "ok" and not records:
        report.status = "empty"
    return source, records, report


async def search_all(
    query: str,
    caller: ToolCaller,
    *,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    types: list[str] | None = None,
    mode: str = "parallel",
    timeout: float | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> SearchBundle:
    """Run the swarm. `mode` is only switched to 'sequential' for benchmarking (Lab 8).

    ``cancel_check`` is invoked before a source is dispatched; it raises
    ``RunCancelled`` when the user has cancelled the run, which also cancels the
    in-flight HTTP requests of the other sources.
    """
    timeout = timeout or 40.0
    started = time.perf_counter()
    results: list[tuple[str, list[ScholarlyRecord], SourceReport]] = []

    if cancel_check is not None:
        cancel_check()  # never start network work for a cancelled run

    if mode == "parallel":
        results = list(
            await asyncio.gather(
                *(
                    _run_one(s, query, limit, year_from, year_to, types, caller, timeout)
                    for s in SOURCES
                )
            )
        )
    else:
        for s in SOURCES:
            if cancel_check is not None:
                cancel_check()
            results.append(await _run_one(s, query, limit, year_from, year_to, types, caller, timeout))

    bundle = SearchBundle(mode=mode, wall_ms=int((time.perf_counter() - started) * 1000))
    for source, records, report in results:
        bundle.reports.append(report)
        bundle.per_source[source] = records
        bundle.records.extend(records)
    log.info(
        "swarm complete mode=%s wall_ms=%s records=%s failed=%s",
        mode,
        bundle.wall_ms,
        len(bundle.records),
        bundle.failed_sources,
    )
    return bundle


async def compare_modes(
    query: str, caller_factory: Callable[[], ToolCaller], **kwargs: Any
) -> dict[str, Any]:
    """Measured sequential-vs-parallel comparison (no invented speedup numbers)."""
    seq = await search_all(query, caller_factory(), mode="sequential", **kwargs)
    par = await search_all(query, caller_factory(), mode="parallel", **kwargs)
    return {
        "query": query,
        "sequential": {
            "wall_ms": seq.wall_ms,
            "per_source": [r.as_dict() for r in seq.reports],
            "records": len(seq.records),
        },
        "parallel": {
            "wall_ms": par.wall_ms,
            "per_source": [r.as_dict() for r in par.reports],
            "records": len(par.records),
        },
        "speedup": round(seq.wall_ms / par.wall_ms, 2) if par.wall_ms else None,
        "note": "Measured back-to-back on the same machine and query; values vary per run.",
    }
