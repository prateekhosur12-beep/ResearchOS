"""Validated input schemas for every callable tool (Lab 2).

These are the single source of truth for tool arguments. They are enforced twice:
once before dispatch (so garbage never leaves the process) and again inside the
MCP server handler (so a direct protocol client cannot bypass validation).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=20, ge=1, le=50)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    types: list[str] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("query must not be blank")
        return v


class DoiInput(BaseModel):
    doi: str = Field(min_length=5, max_length=255)

    @field_validator("doi")
    @classmethod
    def _doi(cls, v: str) -> str:
        v = v.strip()
        for p in ("https://doi.org/", "http://doi.org/", "doi:"):
            if v.lower().startswith(p):
                v = v[len(p):]
        return v


class PaperPayload(BaseModel):
    """Loose scholarly record accepted by tools that take papers inline."""

    source: str = "unknown"
    title: str = Field(min_length=1)
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[dict[str, Any]] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    cited_by: int | None = None
    type: str | None = None
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    id: str | None = None


class CompareInput(BaseModel):
    topic: str = Field(min_length=2, max_length=400)
    papers: list[PaperPayload] = Field(min_length=1, max_length=40)


class MemoryInput(BaseModel):
    project_id: str = Field(min_length=4, max_length=64)
    query: str | None = Field(default=None, max_length=400)
    limit: int = Field(default=10, ge=1, le=50)


class SaveResultsInput(BaseModel):
    project_id: str = Field(min_length=4, max_length=64)
    run_id: str | None = Field(default=None, max_length=64)
    papers: list[PaperPayload] = Field(min_length=0, max_length=200)
    topic: str | None = None


class ReportInput(BaseModel):
    project_id: str = Field(min_length=4, max_length=64)
    include_draft: bool = True
    fmt: Literal["md"] = "md"


class ReadFileInput(BaseModel):
    rel_path: str = Field(min_length=1, max_length=400)
    max_bytes: int = Field(default=200_000, ge=1, le=2_000_000)


class SearchAllInput(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=15, ge=1, le=50)
    year_from: int | None = None
    year_to: int | None = None
    types: list[str] = Field(default_factory=list)


TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "search_openalex": SearchInput,
    "search_crossref": SearchInput,
    "search_arxiv": SearchInput,
    "search_all_sources": SearchAllInput,
    "lookup_doi": DoiInput,
    "get_paper_details": DoiInput,
    "compare_papers": CompareInput,
    "retrieve_project_memory": MemoryInput,
    "save_research_results": SaveResultsInput,
    "generate_research_report": ReportInput,
    "read_research_file": ReadFileInput,
}


class FunderInput(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=8, ge=1, le=25)


class VenueInput(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class CollaboratorInput(BaseModel):
    query: str = Field(min_length=1, max_length=400)
    limit: int = Field(default=10, ge=1, le=25)
    exclude_authors: list[str] = Field(default_factory=list)


TOOL_SCHEMAS.update(
    {
        "find_topic_funders": FunderInput,
        "verify_venue": VenueInput,
        "find_collaborators": CollaboratorInput,
    }
)
