"""Validated tool registry (Lab 2).

The registry is transport-agnostic: the MCP server, the direct in-process path and
the tests all dispatch through the same specs and implementations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.tools.impl import TOOL_IMPLS, summarise_result
from app.tools.specs import TOOL_SCHEMAS

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolValidationError(ValueError):
    pass


class ToolNotFound(KeyError):
    pass


TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_openalex": (
        "Search OpenAlex for scholarly works. Returns live records with DOI, authors, "
        "year, venue, abstract (when available), citation counts and provenance."
    ),
    "search_crossref": (
        "Search Crossref for scholarly works (publisher-deposited metadata). Returns live "
        "records with DOI, authors, year, container title and abstract when deposited."
    ),
    "search_arxiv": (
        "Search arXiv preprints. Returns live Atom records with arXiv id, authors, "
        "submission year, categories and PDF link."
    ),
    "search_all_sources": (
        "Fan out one query to OpenAlex, Crossref and arXiv in parallel, then merge and "
        "deduplicate. Reports per-source status and latency."
    ),
    "lookup_doi": (
        "Resolve a DOI against Crossref (falling back to OpenAlex). Reports whether the "
        "DOI exists; does not judge whether a paper supports a claim."
    ),
    "get_paper_details": "Alias of lookup_doi with a details-oriented payload.",
    "compare_papers": (
        "Compare supplied paper records using only their title/abstract text: method "
        "signals, stated limitations, dataset mentions, venue/year spread."
    ),
    "retrieve_project_memory": (
        "Read stored project memory: topic, saved papers, gaps, drafts and runs. "
        "Optional semantic query restricts the returned papers."
    ),
    "save_research_results": "Persist normalized paper records under a project id (deduplicated).",
    "generate_research_report": "Compose and write a Markdown research report for a project.",
    "read_research_file": "Read a relative file inside the data/ or exports/ directory only.",
    "find_topic_funders": (
        "Report funders and award IDs recorded on real publications for a topic, plus OpenAlex "
        "funder entities. Never returns invented deadlines, amounts or eligibility."
    ),
    "verify_venue": (
        "Verify a venue name against Crossref's journal registry: title, ISSN, publisher, DOI "
        "counts. Impact factor and acceptance rate are explicitly not provided."
    ),
    "find_collaborators": (
        "Identify real authors publishing on a topic from OpenAlex authorship records, with their "
        "papers as evidence. Similarity is not evidence of availability."
    ),
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: type[BaseModel]
    handler: Handler

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema.model_json_schema(),
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ToolNotFound(f"unknown tool '{name}'. Available: {self.names()}")
        return self._tools[name]

    def describe(self) -> list[dict[str, Any]]:
        return [self._tools[n].describe() for n in self.names()]

    def validate(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.get(name)
        try:
            return spec.schema.model_validate(args or {}).model_dump()
        except ValidationError as exc:
            raise ToolValidationError(f"invalid arguments for {name}: {exc}") from exc

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        validated = self.validate(name, args)
        return await self._tools[name].handler(validated)


_registry: ToolRegistry | None = None


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for name, fn in TOOL_IMPLS.items():
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            raise RuntimeError(f"tool '{name}' has no input schema")
        reg.register(
            ToolSpec(
                name=name,
                description=TOOL_DESCRIPTIONS.get(name, "no description"),
                schema=schema,
                handler=fn,
            )
        )
    return reg


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry


__all__ = [
    "ToolRegistry",
    "ToolSpec",
    "ToolValidationError",
    "ToolNotFound",
    "build_registry",
    "get_registry",
    "summarise_result",
    "TOOL_DESCRIPTIONS",
]
