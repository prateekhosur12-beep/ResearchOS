"""Lab 10 — Observability & resilience: retries, backoff, live health."""

from __future__ import annotations

import httpx
import pytest

from app.services.scholarly.http import ScholarHttp, scholar_http


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, text='{"results": []}')

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ScholarHttp, "client", lambda self: _async(client), raising=True)

    http = ScholarHttp()
    res = await http.get_raw(source="openalex", url="https://api.example/works", max_retries=2)
    assert res.status == "ok"
    assert res.attempts == 2, "one retry expected after a 429"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_does_not_retry_client_errors(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="nope")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ScholarHttp, "client", lambda self: _async(client), raising=True)

    http = ScholarHttp()
    res = await http.get_raw(source="crossref", url="https://api.example/works/10.1/missing", max_retries=3)
    assert res.status == "error"
    assert res.http_status == 404
    assert calls["n"] == 1, "404 must not be retried"


@pytest.mark.asyncio
async def test_retry_budget_is_bounded(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ScholarHttp, "client", lambda self: _async(client), raising=True)

    http = ScholarHttp()
    res = await http.get_raw(source="arxiv", url="https://api.example/query", max_retries=2)
    assert res.status == "error"
    assert calls["n"] == 3, "initial call + 2 retries, then stop"


@pytest.mark.asyncio
async def test_timeout_is_reported(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ScholarHttp, "client", lambda self: _async(client), raising=True)
    http = ScholarHttp()
    res = await http.get_raw(source="openalex", url="https://api.example/works", max_retries=0)
    assert res.status in ("timeout", "error")
    assert "timeout" in (res.error or "").lower() or "ReadTimeout" in (res.error or "")


async def _async(obj):
    return obj


def test_health_endpoint_reports_dependencies():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        status = client.get("/api/system/status")
        assert status.status_code == 200
        body = status.json()
        assert "llm" in body and body["llm"]["available"] is False  # closed port in tests
        assert "model" in body["llm"]
        assert len(body["sources"]) == 3
        assert body["config"]["ollama_model"]
        # secrets must never be exposed
        flat = str(body["config"])
        assert "password" not in flat.lower()


@pytest.mark.asyncio
async def test_rate_limited_source_is_cooled_down_instead_of_retried_forever(monkeypatch):
    """A 429 must not cost minutes: after the retry budget we skip the source."""
    from app.services.scholarly import http as http_mod

    calls: list[str] = []

    class FakeResponse:
        status_code = 429
        headers = {"Retry-After": "45"}
        text = ""
        url = "https://api.openalex.org/works"

    class FakeClient:
        async def get(self, url, params=None):
            calls.append(url)
            return FakeResponse()

        @property
        def is_closed(self):
            return False

    client = http_mod.ScholarHttp()
    monkeypatch.setattr(http_mod.settings, "scholarly_throttle_scale", 0.0)
    monkeypatch.setattr(http_mod.settings, "scholarly_max_retries", 1)

    async def fake_client():
        return FakeClient()

    monkeypatch.setattr(client, "client", fake_client)
    monkeypatch.setattr(http_mod.asyncio, "sleep", lambda _s: _noop())

    first = await client.get_raw(source="openalex", url="https://api.openalex.org/works")
    assert first.status == "error" and first.http_status == 429
    assert len(calls) == 2  # initial try + one retry, no more

    second = await client.get_raw(source="openalex", url="https://api.openalex.org/works")
    assert second.status == "rate_limited"
    assert len(calls) == 2, "the cooled-down source must not be called again"
    assert "rate limit" in (second.error or "")


async def _noop() -> None:
    return None
