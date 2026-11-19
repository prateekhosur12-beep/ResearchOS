"""ToolRunner — the single seam through which agents execute tools (Lab 2 + Lab 6).

Responsibilities:
  * pick the transport (real MCP stdio session, or the direct registry)
  * validate arguments before they leave the process
  * record every invocation (tool, transport, args, status, latency) in the DB
  * degrade honestly: if MCP cannot start, fall back to the direct registry and
    say so, rather than reporting a protocol success that never happened
"""

from __future__ import annotations

import time
from typing import Any

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import ToolInvocation
from app.logging_conf import get_logger
from app.mcp.client import McpClient, McpToolError
from app.tools.registry import ToolValidationError, get_registry, summarise_result

log = get_logger("tools.runner")


class ToolRunner:
    def __init__(
        self,
        project_id: str | None = None,
        run_id: str | None = None,
        transport: str | None = None,
        record: bool = True,
    ) -> None:
        self.project_id = project_id
        self.run_id = run_id
        self._force_transport = transport
        self._mcp: McpClient | None = None
        self.record = record
        self.mode = "direct"
        self.transport_note = ""
        self.invocations: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ setup
    async def start(self) -> None:
        want_mcp = settings.mcp_enabled if self._force_transport is None else self._force_transport == "mcp"
        if not want_mcp:
            self.mode = "direct"
            self.transport_note = "MCP disabled by configuration; using in-process registry"
            return
        client = McpClient()
        try:
            await client.start()
            await client.list_tools()
            self._mcp = client
            self.mode = "mcp"
            self.transport_note = (
                f"MCP stdio session to '{client.server_info.get('name','server')}' "
                f"(protocol {client.server_info.get('protocol_version','?')})"
            )
            log.info("tool runner using MCP transport")
        except Exception as exc:  # noqa: BLE001
            await client.aclose()
            self.mode = "direct"
            self.transport_note = f"MCP unavailable ({exc}); fell back to direct registry"
            log.warning(self.transport_note)

    async def aclose(self) -> None:
        if self._mcp is not None:
            await self._mcp.aclose()
            self._mcp = None

    # ------------------------------------------------------------------- call
    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        registry = get_registry()
        started = time.perf_counter()
        status = "ok"
        error: str | None = None
        result: dict[str, Any] = {}

        # Validate first: bad arguments never reach the network or the subprocess.
        try:
            validated = registry.validate(name, args)
        except ToolValidationError as exc:
            await self._record(name, args, "invalid", started, None, str(exc))
            return {"tool": name, "ok": False, "status": "invalid_args", "error": str(exc)}

        try:
            if self._mcp is not None:
                result = await self._mcp.call_tool(name, validated)
            else:
                result = await registry.call(name, validated)
            if isinstance(result, dict) and result.get("status") == "error":
                status = "error"
                error = result.get("error")
        except McpToolError as exc:
            status, error = "error", str(exc)
            result = {"ok": False, "status": "error", "error": str(exc), "tool": name}
        except Exception as exc:  # noqa: BLE001
            status, error = "error", f"{exc.__class__.__name__}: {exc}"
            result = {"ok": False, "status": "error", "error": error, "tool": name}
            log.warning("tool call failed name=%s err=%s", name, error)

        await self._record(name, args, status, started, result, error)
        return result

    async def _record(
        self,
        name: str,
        args: dict[str, Any],
        status: str,
        started: float,
        result: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        latency = int((time.perf_counter() - started) * 1000)
        entry = {
            "tool": name,
            "transport": self.mode,
            "status": status,
            "latency_ms": latency,
            "summary": summarise_result(name, result) if result else (error or ""),
            "args": _trim_args(args),
        }
        self.invocations.append(entry)
        if not self.record:
            return
        try:
            async with SessionLocal() as session:
                session.add(
                    ToolInvocation(
                        project_id=self.project_id,
                        run_id=self.run_id,
                        tool=name,
                        transport=self.mode,
                        args_json=_trim_args(args),
                        status=status,
                        latency_ms=latency,
                        result_summary=(entry["summary"] or "")[:500],
                        error=(error or "")[:500] or None,
                    )
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - telemetry must not break research
            log.warning("failed to record tool invocation: %s", exc)


def _trim_args(args: dict[str, Any]) -> dict[str, Any]:
    """Keep audit records small and free of huge inline payloads."""
    out: dict[str, Any] = {}
    for k, v in args.items():
        if isinstance(v, list):
            out[k] = f"[{len(v)} items]"
        elif isinstance(v, str) and len(v) > 300:
            out[k] = v[:300] + "…"
        else:
            out[k] = v
    return out
