"""Ollama service: availability, model checks, structured output, failure modes."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from app.services.llm import OllamaService, _extract_json, get_llm


class Answer(BaseModel):
    value: int
    label: str


@pytest.mark.asyncio
async def test_unreachable_ollama_is_reported_not_raised():
    svc = OllamaService(base_url="http://127.0.0.1:1", model="qwen2.5:3b", timeout=2)
    health = await svc.health(use_cache=False)
    await svc.close()
    assert health["available"] is False
    assert "Cannot reach Ollama" in health["detail"]
    assert "ollama serve" in health["detail"]


@pytest.mark.asyncio
async def test_chat_reports_connection_failure():
    svc = OllamaService(base_url="http://127.0.0.1:1", model="qwen2.5:3b", timeout=2)
    res = await svc.chat([{"role": "user", "content": "hi"}])
    await svc.close()
    assert res.ok is False
    assert "unreachable" in (res.error or "").lower()
    assert res.label == "unavailable"


@pytest.mark.asyncio
async def test_health_detects_missing_model(fake_ollama):
    fake_ollama["model_installed"] = False
    svc = get_llm()
    health = await svc.health(use_cache=False)
    assert health["available"] is False
    assert "not installed" in health["detail"]
    assert "ollama pull qwen2.5:3b" in health["detail"]


@pytest.mark.asyncio
async def test_structured_output_validated(fake_ollama):
    fake_ollama["chat"] = {"value": 7, "label": "ok"}
    svc = get_llm()
    res = await svc.chat_structured([{"role": "user", "content": "give me json"}], Answer)
    assert res.ok and res.data.value == 7 and res.data.label == "ok"
    assert res.repaired is False


@pytest.mark.asyncio
async def test_structured_output_repairs_once(fake_ollama):
    state = {"n": 0}

    def chat(body):
        state["n"] += 1
        if state["n"] == 1:
            return "this is not json at all"
        return json.dumps({"value": 3, "label": "fixed"})

    fake_ollama["chat"] = chat
    svc = get_llm()
    res = await svc.chat_structured([{"role": "user", "content": "x"}], Answer)
    assert res.ok and res.data.label == "fixed"
    assert res.repaired is True
    assert state["n"] == 2, "exactly one repair attempt"


@pytest.mark.asyncio
async def test_structured_output_gives_up_cleanly(fake_ollama):
    fake_ollama["chat"] = "still not json"
    svc = get_llm()
    res = await svc.chat_structured([{"role": "user", "content": "x"}], Answer)
    assert res.ok is False
    assert "structured output failed" in (res.error or "")
    assert res.data is None


def test_json_extraction_handles_fences():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('prefix {"a": 2} suffix') == {"a": 2}
    assert _extract_json("no json here") is None


@pytest.mark.asyncio
async def test_embed_returns_none_when_disabled_or_missing():
    svc = OllamaService(base_url="http://127.0.0.1:1", timeout=2)
    out = await svc.embed(["hello"])
    await svc.close()
    assert out is None, "chat models do not provide embeddings; None triggers the local fallback"
