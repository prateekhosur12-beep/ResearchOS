"""MCP client: spawns the research MCP server and executes its tools for real.

This is a protocol client, not a facade. It performs MCP `initialize`,
`tools/list` discovery and `tools/call` over stdio JSON-RPC using the official SDK,
and it surfaces protocol/transport failures instead of pretending a call succeeded.

Concurrency note (measured): several `tools/call` requests multiplexed on one
session execute concurrently, which is what makes the Lab 8 swarm a real parallel
fan-out rather than three sequential awaits.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import BACKEND_ROOT, settings
from app.logging_conf import get_logger

log = get_logger("mcp.client")


class McpError(RuntimeError):
    pass


class McpToolError(McpError):
    """The server executed the tool and reported a failure."""


class McpUnavailable(McpError):
    """The server could not be started or the transport died."""


def _server_params() -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_ROOT) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["PYTHONUNBUFFERED"] = "1"
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", settings.mcp_server_module],
        env=env,
        cwd=str(BACKEND_ROOT),
    )


class McpClient:
    """One short-lived MCP session bound to one workflow run."""

    mode = "mcp"

    def __init__(self, call_timeout: float | None = None) -> None:
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: list[dict[str, Any]] = []
        self.call_timeout = call_timeout or settings.mcp_call_timeout
        self.started_at: float | None = None
        self.server_info: dict[str, Any] = {}

    @property
    def started(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        if self._session is not None:
            return
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(_server_params()))
            session = await stack.enter_async_context(ClientSession(read, write))
            init = await asyncio.wait_for(session.initialize(), timeout=45)
            self._session = session
            self._stack = stack
            self.started_at = time.time()
            info = getattr(init, "server_info", getattr(init, "serverInfo", None))
            self.server_info = {
                "name": getattr(info, "name", "unknown"),
                "version": getattr(info, "version", ""),
                "protocol_version": getattr(init, "protocol_version", getattr(init, "protocolVersion", "")),
            }
            log.info("mcp session initialized server=%s", self.server_info)
        except Exception as exc:  # noqa: BLE001
            await stack.aclose()
            self._session = None
            raise McpUnavailable(f"could not start MCP server: {exc}") from exc

    async def list_tools(self, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh and self._tools:
            return self._tools
        if self._session is None:
            await self.start()
        assert self._session is not None
        result = await asyncio.wait_for(self._session.list_tools(), timeout=30)
        self._tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None),
            }
            for t in result.tools
        ]
        return self._tools

    async def call_tool(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._session is None:
            await self.start()
        assert self._session is not None
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, args or {}), timeout=self.call_timeout
            )
        except asyncio.TimeoutError as exc:
            raise McpError(f"MCP call '{name}' timed out after {self.call_timeout}s") from exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise McpError(f"MCP call '{name}' failed: {exc.__class__.__name__}: {exc}") from exc

        text = self._text_of(result)
        if getattr(result, "is_error", False):
            raise McpToolError(f"MCP tool '{name}' returned an error: {text[:400]}")

        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict) and structured:
            if set(structured) == {"result"} and isinstance(structured["result"], (dict, list)):
                return structured["result"] if isinstance(structured["result"], dict) else {"result": structured["result"]}
            return structured
        if not text:
            raise McpError(f"MCP tool '{name}' returned no content")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise McpError(f"MCP tool '{name}' returned non-JSON content: {text[:200]}") from exc
        if not isinstance(parsed, dict):
            return {"result": parsed}
        return parsed

    @staticmethod
    def _text_of(result: Any) -> str:
        parts = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    async def aclose(self) -> None:
        stack, self._stack = self._stack, None
        self._session = None
        if stack is not None:
            try:
                await stack.aclose()
            except Exception as exc:  # noqa: BLE001 - teardown noise must not fail a run
                log.warning("mcp close error: %s", exc)

    async def __aenter__(self) -> "McpClient":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()


async def probe_server() -> dict[str, Any]:
    """Start a throwaway session and report the discovered tool schemas."""
    client = McpClient(call_timeout=20)
    started = time.perf_counter()
    try:
        tools = await client.list_tools()
        return {
            "ok": True,
            "transport": "stdio",
            "protocol": "mcp",
            "server": client.server_info,
            "tools": [t["name"] for t in tools],
            "tool_count": len(tools),
            "startup_ms": int((time.perf_counter() - started) * 1000),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "transport": "stdio",
            "protocol": "mcp",
            "server": {},
            "tools": [],
            "tool_count": 0,
            "startup_ms": int((time.perf_counter() - started) * 1000),
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    finally:
        await client.aclose()
