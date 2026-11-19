"""FastAPI entry point.

Run (Windows PowerShell, from the backend folder):
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import governance, projects, runs, system, workspace
from app.config import settings
from app.db.base import dispose_engine, init_db
from app.logging_conf import configure_logging, get_logger, new_request_id, request_id_ctx

log = get_logger("api")

_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "static" / "ui",      # built by `npm run build`
    Path(__file__).resolve().parents[2] / "frontend" / "dist",  # vite default location
]
FRONTEND_DIST = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    await init_db()
    try:
        from app.services.workflow_service import reconcile_stale_runs

        reconciled = await reconcile_stale_runs()
        if reconciled:
            log.info("reconciled %s interrupted run(s) from a previous process", reconciled)
    except Exception as exc:  # noqa: BLE001 - startup must not fail on reconciliation
        log.warning("run reconciliation failed: %s", exc)
    log.info(
        "startup app=%s db=%s mcp=%s model=%s",
        settings.app_name,
        settings.database_url.split("://")[0],
        settings.mcp_enabled,
        settings.ollama_model,
    )
    try:
        yield
    finally:
        await dispose_engine()
        log.info("shutdown")


app = FastAPI(
    title=f"{settings.app_name} — API",
    version="1.0.0",
    description=(
        "Multi-agent research platform: live literature discovery (OpenAlex/Crossref/arXiv) through "
        "an MCP tool server, gap analysis, grounded drafting, citation auditing and exports. "
        "Local LLM via Ollama with explicit degradation when the model is unavailable."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = new_request_id()
    request_id_ctx.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed = int((time.perf_counter() - started) * 1000)
        log.exception("unhandled error path=%s ms=%s req=%s", request.url.path, elapsed, rid)
        raise
    elapsed = int((time.perf_counter() - started) * 1000)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time-Ms"] = str(elapsed)
    if request.url.path.startswith("/api") and not request.url.path.endswith("/events"):
        log.info("request method=%s path=%s status=%s ms=%s", request.method, request.url.path, response.status_code, elapsed)
    return response


def _jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Validation errors contain non-JSON objects in ``ctx`` (e.g. ValueError)."""
    out: list[dict[str, Any]] = []
    for err in exc.errors():
        item = {k: v for k, v in err.items() if k in ("type", "loc", "msg", "input")}
        item["loc"] = [str(x) for x in err.get("loc", [])]
        if "input" in item:
            item["input"] = str(item["input"])[:300] if not isinstance(item["input"], (int, float, bool, type(None))) else item["input"]
        out.append(item)
    return out


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": _jsonable_errors(exc),
            "hint": "Check field types and constraints. Tool arguments are validated the same way.",
            "request_id": request_id_ctx.get(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled exception path=%s", request.url.path)
    payload: dict[str, Any] = {
        "error": exc.__class__.__name__,
        "detail": str(exc)[:500],
        "path": request.url.path,
        "request_id": request_id_ctx.get(),
    }
    return JSONResponse(status_code=500, content=payload)


app.include_router(system.router)
app.include_router(projects.router)
app.include_router(runs.router)
app.include_router(workspace.router)
app.include_router(governance.router)


@app.get("/api/labs")
async def labs() -> dict[str, Any]:
    """Machine-readable Lab 1–14 map. Every entry names the code that implements it."""
    return {
        "labs": [
            {"lab": 1, "title": "Agent vs chatbot", "files": ["app/agents/discovery.py"], "endpoint": "/api/projects/{id}/runs"},
            {"lab": 2, "title": "Tool-using agent", "files": ["app/tools/registry.py", "app/tools/specs.py", "app/tools/runner.py"], "endpoint": "/api/system/tools"},
            {"lab": 3, "title": "Reusable skills", "files": ["app/skills/"], "endpoint": "/api/projects/{id}/draft/regenerate"},
            {"lab": 4, "title": "Memory and retrieval", "files": ["app/db/models.py", "app/services/embeddings.py"], "endpoint": "/api/projects/{id}/retrieval/search"},
            {"lab": 5, "title": "MCP connector", "files": ["app/mcp/server.py", "app/mcp/client.py"], "endpoint": "/api/system/status"},
            {"lab": 6, "title": "Agent runtime", "files": ["app/runtime/runtime.py"], "endpoint": "/api/runs/{id}/trace"},
            {"lab": 7, "title": "Agentic node graph", "files": ["app/graph/workflow.py"], "endpoint": "/api/runs/{id}/events"},
            {"lab": 8, "title": "Parallel swarm", "files": ["app/services/scholarly/aggregator.py"], "endpoint": "/api/runs/{id}/trace"},
            {"lab": 9, "title": "Deep research", "files": ["app/agents/deep_research.py"], "endpoint": "/api/projects/{id}/deep-research"},
            {"lab": 10, "title": "Observability and resilience", "files": ["app/services/health.py", "app/services/scholarly/http.py"], "endpoint": "/api/system/status"},
            {"lab": 11, "title": "Agentic SDLC structure", "files": ["app/", "tests/"], "endpoint": "/docs"},
            {"lab": 12, "title": "Safety and governance", "files": ["app/agents/citation.py", "app/api/governance.py", "app/runtime/runtime.py"], "endpoint": "/api/projects/{id}/audit"},
            {"lab": 13, "title": "Discipline-specific agents", "files": ["app/agents/domain.py"], "endpoint": "/api/system/domains"},
            {"lab": 14, "title": "Capstone studio", "files": ["frontend/src/"], "endpoint": "/"},
        ]
    }


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
else:

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "app": settings.app_name,
            "api_docs": "/docs",
            "note": (
                "Frontend build not found (looked for backend/static/ui and frontend/dist). Run "
                "'npm install && npm run build' in the "
                "frontend folder, or use the Vite dev server (npm run dev) which proxies /api here."
            ),
        }
