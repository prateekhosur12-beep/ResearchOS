"""Typed workflow state for the research graph (Lab 7)."""

from __future__ import annotations

from typing import Any, TypedDict


class ResearchState(TypedDict, total=False):
    project_id: str
    run_id: str
    topic: str
    domain: str
    config: dict[str, Any]

    # discovery
    plan: dict[str, Any]
    queries: list[str]
    papers: list[dict[str, Any]]
    discovery_stats: dict[str, Any]
    failed_sources: list[str]
    discovery_revisions: int

    # analysis
    gaps: list[dict[str, Any]]
    matrix: list[dict[str, Any]]
    gap_coverage: dict[str, Any]
    ideas: list[dict[str, Any]]
    deep_research: dict[str, Any]

    # writing
    draft: dict[str, Any]
    bibliography: list[dict[str, Any]]
    citation_report: dict[str, Any]
    draft_revisions: int
    citation_feedback: str

    # radar
    radar: dict[str, Any]
    collaborators: dict[str, Any]

    # governance
    approval_status: str
    export_ready: bool
    warnings: list[str]
    errors: list[str]
    stage_log: list[dict[str, Any]]
    final_status: str
