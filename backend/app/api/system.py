"""System, health, configuration and tool-introspection endpoints (Lab 10)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter

from app.agents.domain import list_domains
from app.config import settings
from app.mcp.client import probe_server
from app.services.health import check_scholarly_sources
from app.services.llm import get_llm
from app.tools.registry import get_registry

router = APIRouter(prefix="/api", tags=["system"])

_started_at = time.time()


@router.get("/health")
async def health() -> dict[str, Any]:
    """Fast liveness probe. Does not touch external services."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "1.0.0",
        "uptime_s": round(time.time() - _started_at, 1),
    }


@router.get("/system/status")
async def system_status(probe_mcp: bool = True) -> dict[str, Any]:
    """Real dependency health: Ollama, the three scholarly APIs, and the MCP server."""
    llm = get_llm()
    llm_task = llm.health(use_cache=False)
    sources_task = check_scholarly_sources()
    mcp_task = probe_server() if probe_mcp else asyncio.sleep(0)

    llm_info, sources, mcp_info = await asyncio.gather(llm_task, sources_task, mcp_task)
    db_info = await _database_status()

    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "uptime_s": round(time.time() - _started_at, 1),
        "llm": llm_info,
        "sources": sources,
        "mcp": mcp_info if probe_mcp else {"ok": None, "note": "probe skipped"},
        "tool_transport": "mcp" if settings.mcp_enabled else "direct",
        "database": db_info,
        "embedding": {
            "model": settings.ollama_embed_model,
            "enabled": settings.ollama_embed_enabled,
            "fallback": "deterministic lexical hashing (labelled in every response)",
        },
        "config": settings.public_snapshot(),
        "tools": [t["name"] for t in get_registry().describe()],
    }


@router.get("/system/tools")
async def tools(probe_mcp: bool = False) -> dict[str, Any]:
    """Full tool schemas plus live MCP discovery when reachable."""
    reg = get_registry()
    payload: dict[str, Any] = {"registry": reg.describe(), "registered": len(reg.names())}
    if probe_mcp:
        payload["mcp"] = await probe_server()
    return payload


@router.get("/system/domains")
async def domains() -> dict[str, Any]:
    return {"domains": list_domains(), "default": "computer_science"}


async def _database_status() -> dict[str, Any]:
    """Real database health: driver, reachability, latency and row counts."""
    import time

    from sqlalchemy import func, select, text

    from app.db.base import SessionLocal
    from app.db.models import Paper, Project, WorkflowRun

    started = time.perf_counter()
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            counts = {
                "projects": (await session.execute(select(func.count(Project.id)))).scalar_one(),
                "papers": (await session.execute(select(func.count(Paper.id)))).scalar_one(),
                "runs": (await session.execute(select(func.count(WorkflowRun.id)))).scalar_one(),
            }
        return {
            "connected": True,
            "backend": settings.resolved_database_url.split("://")[0],
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "counts": counts,
            "detail": "ok",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": False,
            "backend": settings.resolved_database_url.split("://")[0],
            "latency_ms": None,
            "counts": {},
            "detail": f"{exc.__class__.__name__}: {exc}",
        }
