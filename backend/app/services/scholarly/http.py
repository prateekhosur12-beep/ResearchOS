"""Reusable HTTP client: timeouts, bounded retries, exponential backoff, rate-limit respect.

Lab 10 requires that non-retryable failures are *not* retried forever, and that
partial failures are surfaced rather than hidden.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings
from app.logging_conf import get_logger

log = get_logger("scholarly.http")

#: Minimum seconds between requests to the same provider.
_MIN_INTERVAL = {"arxiv": 3.0, "openalex": 0.3, "crossref": 0.3}

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class FetchResult:
    source: str
    url: str
    status: str  # ok | empty | error | timeout
    http_status: int | None = None
    latency_ms: int = 0
    payload: Any = None
    error: str | None = None
    attempts: int = 1
    retrieved_at: float = field(default_factory=time.time)


class ScholarHttp:
    """Shared async HTTP client. One instance per process."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_call: dict[str, float] = {}
        #: source -> monotonic deadline while a provider is asking us to back off
        self._cooldown: dict[str, float] = {}
        self._sem = asyncio.Semaphore(settings.scholarly_concurrency)

    async def client(self) -> httpx.AsyncClient:
        # The client is cached per event loop. A pooled connection belongs to the
        # loop that created it, so reusing it after that loop closed (tests, worker
        # restarts) would raise "Event loop is closed" on the next request.
        loop = asyncio.get_running_loop()
        stale = self._client is not None and (self._client.is_closed or self._loop is not loop)
        if stale and self._client is not None and not self._client.is_closed:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001 - the old loop may already be gone
                pass
            self._client = None
        if self._client is None or self._client.is_closed:
            self._loop = loop
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.scholarly_timeout),
                headers={
                    "User-Agent": (
                        f"AgenticResearchAssistant/1.0 (mailto:{settings.scholarly_contact_email})"
                    ),
                    "Accept": "application/json, application/atom+xml;q=0.9, */*;q=0.8",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except RuntimeError:
                # closing a client whose loop is gone is a no-op, not an error
                pass
        self._client = None
        self._loop = None

    async def get_json(
        self,
        *,
        source: str,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
    ) -> tuple[dict[str, Any] | None, FetchResult]:
        raw = await self.get_raw(source=source, url=url, params=params, max_retries=max_retries)
        if raw.status != "ok" or raw.payload is None:
            return None, raw
        try:
            import json

            data = json.loads(raw.payload)
        except Exception as exc:  # noqa: BLE001
            raw.status = "error"
            raw.error = f"invalid JSON from {source}: {exc}"
            return None, raw
        return data, raw

    async def get_raw(
        self,
        *,
        source: str,
        url: str,
        params: dict[str, Any] | None = None,
        max_retries: int | None = None,
    ) -> FetchResult:
        retries = settings.scholarly_max_retries if max_retries is None else max_retries
        attempts = 0
        started = time.perf_counter()

        cooling = self._cooldown.get(source, 0.0) - time.monotonic()
        if cooling > 0:
            # Circuit breaker: the provider already told us to slow down during this
            # run. Fail fast and report it, instead of burning minutes on retries.
            return FetchResult(
                source=source,
                url=url,
                status="rate_limited",
                http_status=429,
                latency_ms=0,
                error=f"{source} rate limit still in effect for {cooling:.0f}s; request skipped",
            )
        last_error: str | None = None
        last_status: int | None = None

        async with self._sem:
            while attempts <= retries:
                attempts += 1
                await self._throttle(source)
                try:
                    client = await self.client()
                    resp = await client.get(url, params=params)
                    last_status = resp.status_code
                    if resp.status_code < 400:
                        text = resp.text
                        if not text.strip():
                            return FetchResult(
                                source=source,
                                url=str(resp.url),
                                status="empty",
                                http_status=resp.status_code,
                                latency_ms=int((time.perf_counter() - started) * 1000),
                                payload=None,
                                attempts=attempts,
                            )
                        return FetchResult(
                            source=source,
                            url=str(resp.url),
                            status="ok",
                            http_status=resp.status_code,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            payload=text,
                            attempts=attempts,
                        )
                    if resp.status_code == 429 and attempts > retries:
                        wait = self._retry_after_seconds(resp.headers.get("Retry-After"))
                        cooldown = min(max(wait, 20.0), 120.0)
                        self._cooldown[source] = time.monotonic() + cooldown
                        log.warning(
                            "source=%s rate limited (Retry-After=%.0fs); skipping it for %.0fs",
                            source,
                            wait,
                            cooldown,
                        )
                    if resp.status_code not in RETRYABLE_STATUS or attempts > retries:
                        return FetchResult(
                            source=source,
                            url=str(resp.url),
                            status="error",
                            http_status=resp.status_code,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            error=f"HTTP {resp.status_code} from {source}",
                            attempts=attempts,
                        )
                    # retryable
                    delay = self._backoff(attempts, resp.headers.get("Retry-After"))
                    log.warning(
                        "retrying source=%s status=%s attempt=%s delay=%.2fs",
                        source,
                        resp.status_code,
                        attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                except (httpx.TimeoutException, TimeoutError) as exc:
                    last_error = f"timeout after {settings.scholarly_timeout}s calling {source}"
                    if attempts > retries:
                        return FetchResult(
                            source=source,
                            url=url,
                            status="timeout",
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            error=f"{last_error} ({exc.__class__.__name__})",
                            attempts=attempts,
                        )
                    await asyncio.sleep(self._backoff(attempts, None))
                except httpx.HTTPError as exc:
                    last_error = f"{exc.__class__.__name__}: {exc}"
                    if attempts > retries:
                        return FetchResult(
                            source=source,
                            url=url,
                            status="error",
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            error=last_error,
                            attempts=attempts,
                        )
                    await asyncio.sleep(self._backoff(attempts, None))

        return FetchResult(
            source=source,
            url=url,
            status="error",
            http_status=last_status,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=last_error or "unknown failure",
            attempts=attempts,
        )

    async def _throttle(self, source: str) -> None:
        """Keep to each provider's published request rate.

        arXiv asks for at most one request every three seconds; OpenAlex and
        Crossref are happier (and less likely to answer 429) with a small gap too.
        Being polite here is cheaper than a retry storm.
        """
        gap = _MIN_INTERVAL.get(source, 0.0) * float(settings.scholarly_throttle_scale)
        if gap <= 0:
            return
        last = self._last_call.get(source)
        now = time.monotonic()
        if last is not None:
            wait = gap - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
        self._last_call[source] = now

    @staticmethod
    def _retry_after_seconds(retry_after: str | None) -> float:
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return 30.0

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 6.0)
            except ValueError:
                pass
        return min(0.5 * (2 ** (attempt - 1)), 8.0)


scholar_http = ScholarHttp()
