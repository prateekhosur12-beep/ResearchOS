"""Pydantic v2 request/response schemas (Lab 11 separation)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.query_planner import (
    MAX_INSTRUCTIONS_CHARS,
    MAX_TOPIC_CHARS,
    normalize_questions,
    sanitize_topic,
)


class ProjectCreate(BaseModel):
    """A project keeps the topic, the brief and the questions strictly separate.

    ``topic`` is a title (≤300 chars). A long research brief belongs in
    ``research_instructions``; it is given to the agents and is never sent to a
    scholarly search API.
    """

    name: str | None = Field(default=None, max_length=300)
    topic: str
    research_instructions: str = ""
    research_questions: list[str] | str = Field(default_factory=list)
    domain: str = "computer_science"

    @field_validator("topic")
    @classmethod
    def _topic(cls, v: str) -> str:
        raw = (v or "").strip()
        if len(raw) > MAX_TOPIC_CHARS:
            cleaned = sanitize_topic(raw)
            raise ValueError(
                "topic must be a short research title (max "
                f"{MAX_TOPIC_CHARS} characters). Move the full brief into "
                "research_instructions; the topic is what appears in reports and queries. "
                f"Suggested title from your input: {cleaned!r}"
            )
        cleaned = sanitize_topic(raw)
        if len(cleaned) < 3:
            raise ValueError("topic must contain at least 3 characters")
        return cleaned

    @field_validator("research_instructions")
    @classmethod
    def _instructions(cls, v: str) -> str:
        text = (v or "").strip()
        if len(text) > MAX_INSTRUCTIONS_CHARS:
            raise ValueError(
                f"research_instructions must be at most {MAX_INSTRUCTIONS_CHARS} characters"
            )
        return text

    @field_validator("research_questions", mode="before")
    @classmethod
    def _questions(cls, v: Any) -> list[str]:
        return normalize_questions(v)

    @model_validator(mode="after")
    def _name(self) -> "ProjectCreate":
        if not self.name or not self.name.strip():
            self.name = self.topic[:120]
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    topic: str | None = None
    research_instructions: str | None = None
    research_questions: list[str] | str | None = None
    domain: str | None = None

    @field_validator("topic")
    @classmethod
    def _topic(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = sanitize_topic(v)
        if len((v or "").strip()) > MAX_TOPIC_CHARS:
            raise ValueError(
                f"topic must be a short research title (max {MAX_TOPIC_CHARS} characters); "
                "use research_instructions for the full brief"
            )
        if len(cleaned) < 3:
            raise ValueError("topic must contain at least 3 characters")
        return cleaned

    @field_validator("research_questions", mode="before")
    @classmethod
    def _questions(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        return normalize_questions(v)


class ProjectOut(BaseModel):
    id: str
    name: str
    topic: str
    domain: str
    status: str
    created_at: str
    updated_at: str
    research_instructions: str = ""
    research_questions: list[str] = Field(default_factory=list)
    paper_count: int = 0
    run_count: int = 0
    draft_count: int = 0
    gap_count: int = 0
    idea_count: int = 0
    last_run_status: str | None = None
    active_run_id: str | None = None

    model_config = {"from_attributes": True}


class RunConfig(BaseModel):
    """User-facing knobs for one research run."""

    result_limit: int = Field(default=20, ge=1, le=50)
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    publication_types: list[str] = Field(default_factory=list)
    min_papers: int = Field(default=5, ge=1, le=50)
    use_cache: bool = False           # explicit opt-in; default is always a live search
    generate_draft: bool = True
    run_radar: bool = True
    run_collaboration: bool = True
    selected_paper_ids: list[str] = Field(default_factory=list)

    @field_validator("result_limit")
    @classmethod
    def _cap(cls, v: int) -> int:
        return min(v, 50)


class RunOut(BaseModel):
    id: str
    project_id: str
    topic: str
    status: str
    stage: str
    llm_available: bool
    stats: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    finished_at: str | None = None


class PaperOut(BaseModel):
    id: str
    title: str
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
    retrieved_at: str
    rank_score: float = 0.0
    rank_explain: dict[str, Any] = Field(default_factory=dict)
    is_selected: bool = False
    metadata_warnings: list[str] = Field(default_factory=list)


class GapOut(BaseModel):
    id: str
    title: str
    description: str
    rationale: str
    kind: str
    confidence: float
    feasibility: str | None = None
    suggested_metrics: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    generated_by: str = "heuristic"


class IdeaOut(BaseModel):
    id: str
    title: str
    research_questions: list[str] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    proposed_methodology: str = ""
    suggested_datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    feasibility: str = ""
    generated_by: str = "heuristic"


class DraftSectionOut(BaseModel):
    name: str
    markdown: str
    generated_by: str = "template"
    citations: list[str] = Field(default_factory=list)
    word_count: int = 0


class DraftOut(BaseModel):
    id: str
    version: int
    status: str
    markdown: str
    sections: list[DraftSectionOut] = Field(default_factory=list)
    generated_by: str = "template"
    updated_at: str


class DraftSectionPatch(BaseModel):
    section: str
    markdown: str


class TrendPoint(BaseModel):
    year: int
    count: int


class LLMStatus(BaseModel):
    provider: str
    available: bool
    model: str
    base_url: str
    detail: str = ""
    models_installed: list[str] = Field(default_factory=list)


class SourceHealth(BaseModel):
    source: str
    status: Literal["ok", "degraded", "down", "unknown"]
    latency_ms: int | None = None
    detail: str = ""
    checked_at: str


class SystemStatus(BaseModel):
    app: str
    version: str
    llm: LLMStatus
    sources: list[SourceHealth]
    mcp: dict[str, Any]
    tool_transport: str
    config: dict[str, Any]
