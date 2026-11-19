"""Shared helpers for agents."""

from __future__ import annotations

import re
from typing import Any

from app.db.models import Paper


def paper_to_dict(p: Paper) -> dict[str, Any]:
    return {
        "id": p.id,
        "title": p.title,
        "doi": p.doi,
        "arxiv_id": p.arxiv_id,
        "authors": p.authors_json or [],
        "year": p.year,
        "venue": p.venue,
        "abstract": p.abstract,
        "url": p.url,
        "pdf_url": p.pdf_url,
        "cited_by": p.cited_by,
        "type": p.type,
        "sources": p.sources_json or [],
        "retrieved_at": p.retrieved_at.isoformat() if p.retrieved_at else None,
        "rank_score": p.rank_score,
        "rank_explain": p.rank_explain_json or {},
        "is_selected": p.is_selected,
    }


def citation_key_for(index: int) -> str:
    return f"P{index + 1}"


def safe_slug(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug[:max_len] or "untitled").strip("-")


def extract_citation_keys(markdown: str) -> list[str]:
    return sorted(set(re.findall(r"\[(P\d+)\]", markdown)))


def author_names(paper: dict[str, Any], limit: int = 3) -> list[str]:
    names = [a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")]
    return names[:limit]
