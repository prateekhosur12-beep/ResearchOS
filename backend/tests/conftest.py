"""Test fixtures.

Two classes of tests:
  * MOCKED (default): external HTTP is replaced by fixtures that reproduce the real
    response shapes. Deterministic, offline, fast.
  * LIVE (@pytest.mark.live): the real OpenAlex/Crossref/arXiv APIs are called.
    Enable with RUN_LIVE_TESTS=1.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import uuid

import pytest

# --- Isolate the test database BEFORE app.config is imported -----------------
_TMP = tempfile.mkdtemp(prefix="ra-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["DATA_DIR"] = f"{_TMP}/data"
os.environ["EXPORT_DIR"] = f"{_TMP}/exports"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"  # guaranteed-closed port
os.environ["OLLAMA_EMBED_ENABLED"] = "0"
# Mocked tests use the direct in-process tool path: the MCP server runs in a
# separate subprocess, so in-process HTTP mocks cannot reach it. Lab 5 tests opt
# back into the real MCP transport explicitly (it is exercised for real there and
# in live runs).
os.environ["MCP_ENABLED"] = "0"
os.environ["REQUIRE_APPROVAL_BEFORE_EXPORT"] = "1"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["SCHOLARLY_THROTTLE_SCALE"] = "0"  # no polite sleeps inside the suite

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.db.base import Base, SessionLocal, engine  # noqa: E402
from app.db import models  # noqa: E402,F401


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE_TESTS") == "1":
        return
    skip_live = pytest.mark.skip(reason="live test: set RUN_LIVE_TESTS=1 to run against real APIs")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(scope="function", autouse=True)
async def fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session():
    async with SessionLocal() as s:
        yield s


@pytest.fixture
async def project(session):
    from app.db.models import Project

    p = Project(
        id=uuid.uuid4().hex,
        name="Test project",
        topic="Road anomaly detection using YOLO",
        domain="computer_science",
    )
    session.add(p)
    await session.commit()
    return p


# --------------------------------------------------------------------------
# Fake scholarly responses (shapes copied from the real APIs)
# --------------------------------------------------------------------------
def _inverted(text: str) -> dict:
    idx: dict[str, list[int]] = {}
    for pos, word in enumerate(text.split()):
        idx.setdefault(word.strip(".,;:"), []).append(pos)
    return idx


def openalex_payload(query: str, n: int = 3) -> dict:
    return {
        "results": [
            {
                "id": f"https://openalex.org/W{i}",
                "doi": f"https://doi.org/10.1000/test.{i}",
                "title": f"{query.title()} study number {i}",
                "publication_year": 2023 + i,
                "type": "article",
                "cited_by_count": 10 * i,
                "open_access": {"is_oa": True, "oa_url": None},
                "authorships": [
                    {
                        "author": {
                            "id": f"https://openalex.org/A{i}",
                            "display_name": f"Author {i}",
                            "orcid": None,
                        },
                        "institutions": [{"display_name": "Test University"}],
                    }
                ],
                "primary_location": {"source": {"display_name": "Journal of Testing"}},
                "abstract_inverted_index": _inverted(
                    f"We study {query}. A limitation is cross-city generalisation."
                ),
                "best_oa_location": {"pdf_url": None},
            }
            for i in range(n)
        ]
    }


def crossref_payload(query: str, n: int = 2) -> dict:
    return {
        "message": {
            "items": [
                {
                    "DOI": f"10.1000/cross.{i}",
                    "title": [f"{query.title()} crossref item {i}"],
                    "author": [{"given": "Ada", "family": f"Lovelace{i}", "affiliation": []}],
                    "abstract": f"<jats:p>We propose a method for {query}. A limitation is cross-city generalisation.</jats:p>",
                    "issued": {"date-parts": [[2024]]},
                    "container-title": ["Crossref Journal"],
                    "type": "journal-article",
                    "is-referenced-by-count": 5 + i,
                    "URL": f"https://doi.org/10.1000/cross.{i}",
                    "link": [],
                    "score": 1.0,
                }
                for i in range(n)
            ]
        }
    }


def arxiv_atom(query: str, n: int = 2) -> str:
    entries = "".join(
        f"""
  <entry>
    <id>http://arxiv.org/abs/2401.0000{i}v1</id>
    <published>2024-01-0{i+1}T00:00:00Z</published>
    <title>{query.title()} preprint {i}</title>
    <summary>We study {query} and report a limitation in generalisation.</summary>
    <author><name>Grace Hopper {i}</name></author>
    <link title="pdf" href="https://arxiv.org/pdf/2401.0000{i}v1"/>
    <category term="cs.CV"/>
  </entry>"""
        for i in range(n)
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">{entries}
</feed>"""


class FakeScholar:
    """Stand-in for ScholarHttp that reproduces the real adapters' inputs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.fail_sources: set[str] = set()
        self.empty_sources: set[str] = set()
        self.delay = 0.0

    async def get_json(self, *, source, url, params=None, max_retries=None):
        from app.services.scholarly.http import FetchResult

        self.calls.append((source, url, params or {}))
        if source in self.fail_sources:
            return None, FetchResult(
                source=source, url=url, status="error", http_status=503,
                latency_ms=1, error=f"HTTP 503 from {source}", attempts=1,
            )
        if source in self.empty_sources:
            return None, FetchResult(source=source, url=url, status="empty", http_status=200, latency_ms=1, payload=None)
        query = (params or {}).get("search") or (params or {}).get("query.bibliographic") or "test"
        if "journals" in url:
            return {"message": {"items": [{"title": query, "publisher": "Test Publisher", "ISSN": ["1234-5678"], "counts": {"total-dois": 100}}]}}, FetchResult(
                source=source, url=url, status="ok", http_status=200, latency_ms=2, payload="{}"
            )
        if "funders" in url:
            return {"results": [{"id": "https://openalex.org/F1", "display_name": "Test Funder", "country_code": "IN",
                                 "homepage_url": "https://funder.example", "awards_count": 3, "works_count": 90}]}, FetchResult(
                source=source, url=url, status="ok", http_status=200, latency_ms=2, payload="{}"
            )
        # Single-record DOI lookups:  /works/10.xxxx/yyy  or  /works/https://doi.org/...
        if "/works/" in url:
            tail = url.split("/works/", 1)[1]
            doi = tail.replace("https://doi.org/", "").strip("/")
            if not doi.startswith("10."):
                return None, FetchResult(
                    source=source, url=url, status="error", http_status=404, latency_ms=1,
                    error="HTTP 404 from registry", attempts=1,
                )
            record = {
                "DOI": doi,
                "title": [f"Resolved title for {doi}"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "abstract": "Resolved abstract.",
                "issued": {"date-parts": [[2024]]},
                "container-title": ["Resolved Journal"],
                "type": "journal-article",
                "is-referenced-by-count": 3,
                "URL": f"https://doi.org/{doi}",
                "link": [],
            }
            if source == "crossref":
                return {"message": record, "status": "ok"}, FetchResult(
                    source=source, url=url, status="ok", http_status=200, latency_ms=2, payload="{}"
                )
            return {
                "id": f"https://openalex.org/W{abs(hash(doi)) % 9999}",
                "doi": f"https://doi.org/{doi}",
                "title": f"Resolved title for {doi}",
                "publication_year": 2024,
                "type": "article",
                "cited_by_count": 3,
                "open_access": {"is_oa": True},
                "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace"},
                                 "institutions": []}],
                "primary_location": {"source": {"display_name": "Resolved Journal"}},
            }, FetchResult(source=source, url=url, status="ok", http_status=200, latency_ms=2, payload="{}")

        if source == "openalex":
            return openalex_payload(query), FetchResult(
                source=source, url=url, status="ok", http_status=200, latency_ms=3, payload="{}"
            )
        if source == "crossref":
            return crossref_payload(query), FetchResult(
                source=source, url=url, status="ok", http_status=200, latency_ms=3, payload="{}"
            )
        return {"results": []}, FetchResult(source=source, url=url, status="empty", http_status=200, latency_ms=1, payload="{}")

    async def get_raw(self, *, source, url, params=None, max_retries=None):
        from app.services.scholarly.http import FetchResult

        self.calls.append((source, url, params or {}))
        if source in self.fail_sources:
            return FetchResult(source=source, url=url, status="error", http_status=500, latency_ms=1,
                               error=f"HTTP 500 from {source}", attempts=1)
        query = (params or {}).get("search_query") or "test"
        return FetchResult(source=source, url=url, status="ok", http_status=200, latency_ms=2,
                           payload=arxiv_atom(query), attempts=1)


@pytest.fixture
def fake_scholar(monkeypatch):
    fake = FakeScholar()
    import app.services.scholarly.http as http_mod

    monkeypatch.setattr(http_mod, "scholar_http", fake)
    # adapters imported the singleton by name -> patch where used
    for mod_name in (
        "app.services.scholarly.openalex",
        "app.services.scholarly.crossref",
        "app.services.scholarly.arxiv",
    ):
        mod = __import__(mod_name, fromlist=["scholar_http"])
        monkeypatch.setattr(mod, "scholar_http", fake)
    return fake


# --------------------------------------------------------------------------
# Fake Ollama (httpx MockTransport) — lets us test the LLM paths deterministically
# --------------------------------------------------------------------------
@pytest.fixture
def fake_ollama(monkeypatch):
    import httpx

    from app.services.llm import OllamaService, get_llm

    state = {"available": True, "model_installed": True, "chat": None, "fail": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            if state["fail"]:
                raise httpx.ConnectError("connection refused", request=request)
            models = [{"name": "qwen2.5:3b"}] if state["model_installed"] else [{"name": "llama3:8b"}]
            return httpx.Response(200, json={"models": models})
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            reply = state["chat"]
            if callable(reply):
                reply = reply(body)
            if reply is None:
                reply = {"analyses": []}
            text = reply if isinstance(reply, str) else json.dumps(reply)
            return httpx.Response(200, json={"model": body.get("model", "qwen2.5:3b"), "message": {"content": text}})
        if request.url.path == "/api/embed":
            body = json.loads(request.content)
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3] for _ in body["input"]]})
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)

    async def patched_client(self):
        return httpx.AsyncClient(base_url=self.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(OllamaService, "client", patched_client)
    svc = OllamaService()
    monkeypatch.setattr("app.services.llm._llm_singleton", svc)
    import app.agents.discovery as disc

    monkeypatch.setattr(disc, "get_llm", lambda: svc)
    return state


@pytest.fixture
def anyio_backend():
    return "asyncio"
