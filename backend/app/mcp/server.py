"""Genuine Model Context Protocol server (Lab 5).

Transport: stdio (JSON-RPC 2.0 per the MCP spec), implemented with the official
`mcp` Python SDK (`MCPServer` in mcp>=2, formerly FastMCP).

Run standalone:
    python -m app.mcp.server

The same tool implementations back the direct registry, so behaviour is identical
whichever transport the application uses.
"""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.config import settings
from app.db.base import dispose_engine, init_db
from app.logging_conf import configure_logging, get_logger
from app.tools.impl import TOOL_IMPLS
from app.tools.registry import ToolValidationError

log = get_logger("mcp.server")


@asynccontextmanager
async def lifespan(_server: MCPServer):
    configure_logging()
    await init_db()
    log.info("mcp server ready model=%s", settings.ollama_model)
    try:
        yield {}
    finally:
        await dispose_engine()


server = MCPServer(
    name="agentic-research-tools",
    version="1.0.0",
    instructions=(
        "Scholarly research tools for the Agentic AI Research Assistant. "
        "All search tools return live records from OpenAlex, Crossref and arXiv. "
        "A tool never fabricates records: check the 'status' field of every response."
    ),
    lifespan=lifespan,
)


def _jsonable(result: Any) -> Any:
    return json.loads(json.dumps(result, default=str))


async def _dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        return _jsonable(await TOOL_IMPLS[name](args))
    except ToolValidationError as exc:
        return {"tool": name, "ok": False, "status": "error", "error": str(exc), "invalid_args": True}
    except Exception as exc:  # noqa: BLE001
        log.exception("tool failed name=%s", name)
        return {
            "tool": name,
            "ok": False,
            "status": "error",
            "error": f"{exc.__class__.__name__}: {exc}",
        }


@server.tool()
async def search_openalex(
    query: str, limit: int = 20, year_from: int | None = None, year_to: int | None = None
) -> dict:
    """Search OpenAlex live. Returns records plus status/latency/provenance."""
    return await _dispatch(
        "search_openalex",
        {"query": query, "limit": limit, "year_from": year_from, "year_to": year_to},
    )


@server.tool()
async def search_crossref(
    query: str, limit: int = 20, year_from: int | None = None, year_to: int | None = None
) -> dict:
    """Search Crossref live. Returns records plus status/latency/provenance."""
    return await _dispatch(
        "search_crossref",
        {"query": query, "limit": limit, "year_from": year_from, "year_to": year_to},
    )


@server.tool()
async def search_arxiv(
    query: str, limit: int = 20, year_from: int | None = None, year_to: int | None = None
) -> dict:
    """Search arXiv live. Returns records plus status/latency/provenance."""
    return await _dispatch(
        "search_arxiv",
        {"query": query, "limit": limit, "year_from": year_from, "year_to": year_to},
    )


@server.tool()
async def search_all_sources(
    query: str, limit: int = 15, year_from: int | None = None, year_to: int | None = None
) -> dict:
    """Fan out to all three sources in parallel, merge and deduplicate."""
    return await _dispatch(
        "search_all_sources",
        {"query": query, "limit": limit, "year_from": year_from, "year_to": year_to},
    )


@server.tool()
async def lookup_doi(doi: str) -> dict:
    """Resolve a DOI via Crossref (fallback OpenAlex). Reports found/not-found honestly."""
    return await _dispatch("lookup_doi", {"doi": doi})


@server.tool()
async def get_paper_details(doi: str) -> dict:
    """Fetch full metadata for one paper by DOI."""
    return await _dispatch("get_paper_details", {"doi": doi})


@server.tool()
async def compare_papers(topic: str, papers: list[dict]) -> dict:
    """Deterministic comparison of supplied paper records (no invented attributes)."""
    return await _dispatch("compare_papers", {"topic": topic, "papers": papers})


@server.tool()
async def retrieve_project_memory(project_id: str, query: str | None = None, limit: int = 10) -> dict:
    """Read stored project memory (papers, gaps, drafts) for one project id."""
    return await _dispatch(
        "retrieve_project_memory", {"project_id": project_id, "query": query, "limit": limit}
    )


@server.tool()
async def save_research_results(
    project_id: str, papers: list[dict], run_id: str | None = None, topic: str | None = None
) -> dict:
    """Persist paper records under a project id, deduplicated by DOI/arXiv/title."""
    return await _dispatch(
        "save_research_results",
        {"project_id": project_id, "papers": papers, "run_id": run_id, "topic": topic},
    )


@server.tool()
async def generate_research_report(project_id: str, include_draft: bool = True) -> dict:
    """Write a Markdown research report for a project to the exports directory."""
    return await _dispatch(
        "generate_research_report", {"project_id": project_id, "include_draft": include_draft}
    )


@server.tool()
async def read_research_file(rel_path: str, max_bytes: int = 200_000) -> dict:
    """Read a relative file from data/ or exports/ only. Path traversal is rejected."""
    return await _dispatch("read_research_file", {"rel_path": rel_path, "max_bytes": max_bytes})


@server.tool()
async def find_topic_funders(query: str, limit: int = 8) -> dict:
    """Funders and award IDs recorded on real publications for a topic (not open calls)."""
    return await _dispatch("find_topic_funders", {"query": query, "limit": limit})


@server.tool()
async def verify_venue(name: str, limit: int = 5) -> dict:
    """Verify a journal/venue name against Crossref's registry (ISSN, publisher)."""
    return await _dispatch("verify_venue", {"name": name, "limit": limit})


@server.tool()
async def find_collaborators(query: str, limit: int = 10, exclude_authors: list[str] | None = None) -> dict:
    """Find researchers active on a topic from real authorship records."""
    return await _dispatch(
        "find_collaborators",
        {"query": query, "limit": limit, "exclude_authors": exclude_authors or []},
    )


def main() -> None:
    # stdout is the JSON-RPC channel: logging must go to stderr.
    configure_logging()
    server.run(transport="stdio")


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] not in ("--stdio",):
        print(f"unknown args: {sys.argv[1:]}", file=sys.stderr)
    main()
