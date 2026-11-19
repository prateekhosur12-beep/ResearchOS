"""Reusable skill contract (Lab 3).

A skill is a *procedural* capability with a declared input schema, declared tool
needs, an output schema enforced at runtime, and an explicit generation label so
consumers can tell model-written content from deterministic extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.services.llm import LLMResult, get_llm


@dataclass
class SkillResult:
    ok: bool
    data: dict[str, Any]
    generated_by: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    llm_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "generated_by": self.generated_by,
            "warnings": self.warnings,
            "error": self.error,
            "llm_used": self.llm_used,
        }


class Skill:
    """Base class. Subclasses declare metadata and implement `grounded_fallback`
    plus, optionally, `llm_schema` + `build_messages` to enable the LLM path."""

    name: str = "skill"
    description: str = ""
    instructions: str = ""
    required_tools: tuple[str, ...] = ()
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    llm_schema: type[BaseModel] | None = None
    temperature: float = 0.2
    max_tokens: int | None = None
    # When the LLM path fails validation, fall back to deterministic extraction
    # (True) or surface the failure (False).
    fallback_on_llm_failure: bool = True

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "required_tools": list(self.required_tools),
            "input_schema": self.input_schema.model_json_schema() if self.input_schema else None,
            "output_schema": self.output_schema.model_json_schema() if self.output_schema else None,
            "llm_enabled": self.llm_schema is not None,
        }

    def validate_input(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.input_schema is None:
            return payload
        try:
            return self.input_schema.model_validate(payload).model_dump()
        except ValidationError as exc:
            raise ValueError(f"invalid input for skill '{self.name}': {exc}") from exc

    def build_messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        raise NotImplementedError

    async def grounded_fallback(self, payload: dict[str, Any], note: str) -> SkillResult:
        raise NotImplementedError

    async def run(self, payload: dict[str, Any]) -> SkillResult:
        data = self.validate_input(payload)
        if self.llm_schema is None:
            return await self.grounded_fallback(data, "deterministic skill (no model step by design)")

        llm = get_llm()
        health = await llm.health()
        if not health.get("available"):
            return await self.grounded_fallback(
                data, f"LLM unavailable — {health.get('detail', '')}"
            )

        result: LLMResult = await llm.chat_structured(
            self.build_messages(data),
            self.llm_schema,
            temperature=self.temperature,
            num_predict=self.max_tokens,
        )
        if not result.ok:
            if self.fallback_on_llm_failure:
                fallback = await self.grounded_fallback(
                    data, f"LLM call failed ({result.error}) — using deterministic extraction"
                )
                fallback.error = result.error
                return fallback
            return SkillResult(
                ok=False,
                data={},
                generated_by="unavailable",
                error=result.error,
            )

        parsed = result.data
        data_out = parsed.model_dump() if isinstance(parsed, BaseModel) else dict(parsed)
        if self.output_schema is not None:
            try:
                self.output_schema.model_validate(data_out)
            except ValidationError as exc:
                if self.fallback_on_llm_failure:
                    fallback = await self.grounded_fallback(
                        data, f"LLM output failed output validation ({exc.error_count()} errors)"
                    )
                    return fallback
                return SkillResult(ok=False, data=data_out, generated_by="unavailable", error=str(exc))

        return SkillResult(
            ok=True,
            data=data_out,
            generated_by=f"ollama:{result.model}",
            warnings=["model-generated content — verify against the cited sources"],
            llm_used=True,
        )
