"""Scholarly-source health checks with tiny, cheap probe requests (Lab 10)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.config import settings
from app.services.scholarly.http import scholar_http


async def _probe(source: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    res = await scholar_http.get_raw(source=source, url=url, params=params, max_retries=0)
    status = "ok" if res.status in ("ok", "empty") else ("down" if res.status in ("error", "timeout") else "degraded")
    return {
        "source": source,
        "status": status,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "detail": res.error or f"HTTP {res.http_status}",
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def check_scholarly_sources() -> list[dict[str, Any]]:
    return list(
        await asyncio.gather(
            _probe(
                "openalex",
                f"{settings.openalex_base_url}/works",
                {"search": "test", "per-page": 1, "mailto": settings.scholarly_contact_email},
            ),
            _probe(
                "crossref",
                f"{settings.crossref_base_url}/works",
                {"query": "test", "rows": 1, "mailto": settings.scholarly_contact_email},
            ),
            _probe(
                "arxiv",
                f"{settings.arxiv_base_url}/query",
                {"search_query": "all:test", "max_results": 1},
            ),
        )
    )
