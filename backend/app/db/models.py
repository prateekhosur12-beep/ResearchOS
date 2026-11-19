"""Database models. Every research record is scoped to a project_id (Lab 4/§7)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(64), default="computer_science")
    # A project owns four separate fields. Only ``topic`` is ever used for reports;
    # ``research_instructions`` is a brief for the agents and is never sent to a
    # scholarly API (see app/services/query_planner.py).
    research_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_questions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    papers: Mapped[list["Paper"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class WorkflowRun(Base):
    """One execution of the research workflow for one project (Lab 6/7)."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | running | awaiting_approval | completed | failed | cancelled | partial
    stage: Mapped[str] = mapped_column(String(64), default="created")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stats_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_available: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="runs")
    attempts: Mapped[list["SourceAttempt"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    trace: Mapped[list["TraceEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class SourceAttempt(Base):
    """Per-source execution record: status, latency, counts (Lab 8/10)."""

    __tablename__ = "source_attempts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(32))
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")  # ok | error | empty | timeout
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(16), default="mcp")  # mcp | direct
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[WorkflowRun] = relationship(back_populates="attempts")


class Paper(Base):
    """Normalized scholarly record, always project-scoped."""

    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("project_id", "dedupe_key", name="uq_paper_project_dedupe"),
        Index("ix_papers_project_year", "project_id", "year"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    dedupe_key: Mapped[str] = mapped_column(String(280), nullable=False)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    norm_title: Mapped[str] = mapped_column(String(280), nullable=False)
    authors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cited_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    open_access: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # provenance
    sources_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_queries_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # explainable ranking
    rank_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank_explain_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="papers")


class PaperVector(Base):
    """Embeddings for semantic retrieval (Lab 4). Stored separately, rebuildable."""

    __tablename__ = "paper_vectors"
    __table_args__ = (Index("ix_vec_project_paper", "project_id", "paper_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    paper_id: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(96))
    dim: Mapped[int] = mapped_column(Integer)
    vector_json: Mapped[list[float]] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchGap(Base):
    __tablename__ = "research_gaps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_paper_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_quotes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    kind: Mapped[str] = mapped_column(String(24), default="hypothesis")  # evidence_backed | hypothesis
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    feasibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_metrics: Mapped[list[str]] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(96), default="heuristic")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchIdea(Base):
    __tablename__ = "research_ideas"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    research_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    proposed_methodology: Mapped[str] = mapped_column(Text, default="")
    suggested_datasets: Mapped[list[str]] = mapped_column(JSON, default=list)
    metrics: Mapped[list[str]] = mapped_column(JSON, default=list)
    challenges: Mapped[list[str]] = mapped_column(JSON, default=list)
    feasibility: Mapped[str] = mapped_column(Text, default="")
    supporting_paper_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(96), default="heuristic")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft | approved | rejected
    generated_by: Mapped[str] = mapped_column(String(96), default="template")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CitationReport(Base):
    __tablename__ = "citation_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checked: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RadarResult(Base):
    """Journals / funding opportunities (Lab 5 agent). Only verified fields are trusted."""

    __tablename__ = "radar_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(24))  # journal | funding
    name: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verification: Mapped[str] = mapped_column(String(24), default="unverified")  # verified | unverified
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Collaborator(Base):
    __tablename__ = "collaborators"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(Text)
    author_key: Mapped[str | None] = mapped_column(String(255), nullable=True)  # OpenAlex author id
    works_count: Mapped[int] = mapped_column(Integer, default=0)
    relevant_papers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_note: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(32))  # draft | gap_report | export
    artifact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gate: Mapped[str] = mapped_column(String(48), default="publication")
    status: Mapped[str] = mapped_column(String(24), default="pending")  # pending | approved | rejected
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(96), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TraceEvent(Base):
    """Agent runtime execution log (Lab 6)."""

    __tablename__ = "trace_events"
    __table_args__ = (Index("ix_trace_run_seq", "run_id", "seq"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    agent: Mapped[str] = mapped_column(String(64))
    step: Mapped[str] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(24), default="started")
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[WorkflowRun] = relationship(back_populates="trace")


class AuditRecord(Base):
    """Hash-chained audit log (Lab 12).

    Each row commits to the previous row's hash. Deleting or editing a row breaks
    verification of every later row, so the chain is *tamper-evident* when the
    verifier is run. It is NOT immutable storage: the DB file is writable.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_project_seq", "project_id", "seq"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(96), default="system")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExportRecord(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(48))
    filename: Mapped[str] = mapped_column(String(255))
    rel_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    approved_by: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SearchCache(Base):
    """Keyed by source + normalized query + filters. Original retrieval time is kept."""

    __tablename__ = "search_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_cache_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    cache_key: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolInvocation(Base):
    """Per-tool execution record (Lab 2). Proves which tool ran, its status and source."""

    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    tool: Mapped[str] = mapped_column(String(96))
    transport: Mapped[str] = mapped_column(String(24), default="mcp")  # mcp | direct
    args_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="ok")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
