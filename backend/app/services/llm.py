"""Single point of contact for the local LLM (Ollama). Every agent goes through here.

Design rules (from the brief):
  * one reusable service, configurable model + endpoint, explicit timeouts
  * connection failures and "model not installed" are distinguishable errors
  * structured output is validated, with one bounded repair attempt
  * the frontend never learns anything provider-specific

Nothing here invents model output. If the model is unreachable, callers get
ok=False and must fall back to a deterministic path that is labelled as such.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.logging_conf import get_logger

log = get_logger("llm")


class LLMUnavailable(RuntimeError):
    """Ollama is not running / not reachable."""


class LLMModelMissing(RuntimeError):
    """Ollama is up but the requested model is not pulled."""


class LLMTimeout(RuntimeError):
    pass


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    data: Any = None
    model: str = ""
    error: str | None = None
    latency_ms: int = 0
    repaired: bool = False
    raw_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"ollama:{self.model}" if self.ok else "unavailable"


class OllamaService:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout
        self._client: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._health_cache: tuple[float, dict[str, Any]] | None = None
        self._health_ttl = 15.0

    async def client(self) -> httpx.AsyncClient:
        # Cached per event loop: a connection pool cannot be reused on another loop.
        loop = asyncio.get_running_loop()
        if self._client is not None and (self._client.is_closed or self._loop is not loop):
            if not self._client.is_closed:
                try:
                    await self._client.aclose()
                except Exception:  # noqa: BLE001
                    pass
            self._client = None
        if self._client is None or self._client.is_closed:
            self._loop = loop
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except RuntimeError:
                pass
        self._client = None
        self._loop = None

    # ------------------------------------------------------------------ health
    async def health(self, use_cache: bool = True) -> dict[str, Any]:
        now = time.time()
        if use_cache and self._health_cache and now - self._health_cache[0] < self._health_ttl:
            return self._health_cache[1]
        info: dict[str, Any] = {
            "provider": settings.llm_provider,
            "available": False,
            "model": self.model,
            "base_url": self.base_url,
            "models_installed": [],
            "detail": "",
        }
        try:
            client = await self.client()
            resp = await client.get("/api/tags", timeout=5.0)
            resp.raise_for_status()
            data = resp.json()
            installed = [m.get("name", "") for m in data.get("models", [])]
            info["models_installed"] = installed
            info["available"] = True
            # Ollama reports names as "qwen2.5:3b" but ":latest" may be omitted
            match = any(
                m == self.model or m.split(":")[0] == self.model.split(":")[0] for m in installed
            )
            if not match:
                info["detail"] = (
                    f"Ollama is running but model '{self.model}' is not installed. "
                    f"Run: ollama pull {self.model}"
                )
                info["available"] = False
            else:
                info["detail"] = "ok"
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            info["detail"] = (
                f"Cannot reach Ollama at {self.base_url} ({exc.__class__.__name__}). "
                "Start it with: ollama serve"
            )
        except Exception as exc:  # noqa: BLE001
            info["detail"] = f"Ollama health check failed: {exc.__class__.__name__}: {exc}"
        self._health_cache = (now, info)
        return info

    async def is_available(self) -> bool:
        return bool((await self.health()).get("available"))

    # -------------------------------------------------------------------- chat
    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        temperature: float = 0.2,
        timeout: float | None = None,
        num_predict: int | None = None,
    ) -> LLMResult:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        if num_predict:
            payload["options"]["num_predict"] = num_predict

        try:
            client = await self.client()
            resp = await client.post(
                "/api/chat", json=payload, timeout=timeout or self.timeout
            )
            latency = int((time.perf_counter() - started) * 1000)
            if resp.status_code == 404:
                body = resp.text[:300]
                return LLMResult(
                    ok=False,
                    model=self.model,
                    latency_ms=latency,
                    error=f"model '{self.model}' not found in Ollama (404). {body}",
                )
            resp.raise_for_status()
            data = resp.json()
            text = ((data.get("message") or {}).get("content") or "").strip()
            return LLMResult(
                ok=bool(text),
                text=text,
                model=data.get("model", self.model),
                latency_ms=latency,
                error=None if text else "empty completion",
                raw_meta={
                    "eval_count": data.get("eval_count"),
                    "total_duration_ns": data.get("total_duration"),
                    "done_reason": data.get("done_reason"),
                },
            )
        except httpx.ConnectError as exc:
            return LLMResult(
                ok=False,
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"Ollama unreachable at {self.base_url}: {exc}",
            )
        except (httpx.ReadTimeout, asyncio.TimeoutError):
            return LLMResult(
                ok=False,
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"Ollama request timed out after {timeout or self.timeout}s",
            )
        except httpx.HTTPStatusError as exc:
            return LLMResult(
                ok=False,
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:200]}",
            )
        except Exception as exc:  # noqa: BLE001
            return LLMResult(
                ok=False,
                model=self.model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"{exc.__class__.__name__}: {exc}",
            )

    # --------------------------------------------------------- structured call
    async def chat_structured(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        *,
        temperature: float = 0.1,
        timeout: float | None = None,
        num_predict: int | None = None,
    ) -> LLMResult:
        """Ask for JSON, validate against a Pydantic schema, repair once if needed."""
        sys_hint = (
            "Respond with a single valid JSON object only. No prose, no markdown fences. "
            f"The JSON must satisfy this schema:\n{json.dumps(schema.model_json_schema())[:2500]}"
        )
        msgs = list(messages)
        if msgs and msgs[0]["role"] == "system":
            msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n\n" + sys_hint}
        else:
            msgs.insert(0, {"role": "system", "content": sys_hint})

        first = await self.chat(
            msgs, json_mode=True, temperature=temperature, timeout=timeout, num_predict=num_predict
        )
        if not first.ok:
            return first
        parsed = _extract_json(first.text)
        if parsed is not None:
            try:
                return LLMResult(
                    ok=True,
                    text=first.text,
                    data=schema.model_validate(parsed),
                    model=first.model,
                    latency_ms=first.latency_ms,
                    raw_meta=first.raw_meta,
                )
            except ValidationError as exc:
                first_error = str(exc)[:400]
        else:
            first_error = "response was not parseable JSON"

        # one bounded repair attempt
        repair = await self.chat(
            msgs
            + [
                {"role": "assistant", "content": first.text[:1500]},
                {
                    "role": "user",
                    "content": (
                        "That output failed validation with: "
                        f"{first_error}. Return ONLY corrected JSON matching the schema."
                    ),
                },
            ],
            json_mode=True,
            temperature=0.0,
            timeout=timeout,
            num_predict=num_predict,
        )
        if repair.ok:
            parsed = _extract_json(repair.text)
            if parsed is not None:
                try:
                    return LLMResult(
                        ok=True,
                        text=repair.text,
                        data=schema.model_validate(parsed),
                        model=repair.model,
                        latency_ms=first.latency_ms + repair.latency_ms,
                        repaired=True,
                    )
                except ValidationError as exc:
                    return LLMResult(
                        ok=False,
                        model=repair.model,
                        latency_ms=first.latency_ms + repair.latency_ms,
                        error=f"structured output invalid after repair: {str(exc)[:300]}",
                    )
        return LLMResult(
            ok=False,
            model=first.model,
            latency_ms=first.latency_ms + repair.latency_ms,
            error=f"structured output failed: {first_error}",
        )

    # -------------------------------------------------------------- embeddings
    async def embed(self, texts: list[str], model: str | None = None) -> list[list[float]] | None:
        if not settings.ollama_embed_enabled or not texts:
            return None
        embed_model = model or settings.ollama_embed_model
        try:
            client = await self.client()
            resp = await client.post(
                "/api/embed", json={"model": embed_model, "input": texts}, timeout=self.timeout
            )
            if resp.status_code >= 400:
                log.warning("ollama embed failed status=%s", resp.status_code)
                return None
            data = resp.json()
            vectors = data.get("embeddings")
            if vectors and len(vectors) == len(texts):
                return vectors
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("ollama embed unavailable: %s", exc)
            return None


def _extract_json(text: str) -> Any | None:
    """Tolerant JSON extraction: raw object, fenced block, or first {...} span."""
    if not text:
        return None
    candidates = [text.strip()]
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        candidates.append(fence.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    return None


_llm_singleton: OllamaService | None = None


def get_llm() -> OllamaService:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = OllamaService()
    return _llm_singleton
