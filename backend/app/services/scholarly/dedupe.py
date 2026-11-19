"""Merge duplicate records using DOI, arXiv id and normalized title (union-find)."""

from __future__ import annotations

from typing import Any

from app.services.scholarly.records import ScholarlyRecord


class _DSU:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def deduplicate(records: list[ScholarlyRecord]) -> tuple[list[ScholarlyRecord], dict[str, Any]]:
    """Return merged records plus provenance statistics."""
    if not records:
        return [], {"input": 0, "unique": 0, "merged": 0, "by_doi": 0, "by_arxiv": 0, "by_title": 0}

    dsu = _DSU()

    def keys_of(idx: int) -> list[str]:
        return sorted(records[idx].secondary_keys()) or [f"idx:{idx}"]

    # Union all identity keys of each record: any shared key merges two records.
    for idx in range(len(records)):
        keys = keys_of(idx)
        base = f"k:{keys[0]}"
        for key in keys[1:]:
            dsu.union(base, f"k:{key}")

    # Group records by the component of their strongest key.
    groups: dict[str, list[int]] = {}
    for idx in range(len(records)):
        root = dsu.find(f"k:{keys_of(idx)[0]}")
        groups.setdefault(root, []).append(idx)

    merged: list[ScholarlyRecord] = []
    merge_reasons = {"doi": 0, "arxiv": 0, "title": 0}
    for members in groups.values():
        if len(members) == 1:
            merged.append(records[members[0]])
            continue
        merged.append(_merge_group([records[i] for i in members], merge_reasons))

    stats = {
        "input": len(records),
        "unique": len(merged),
        "merged": len(records) - len(merged),
        "merge_reasons": merge_reasons,
    }
    return merged, stats


def _merge_group(group: list[ScholarlyRecord], merge_reasons: dict[str, int]) -> ScholarlyRecord:
    # Score each record for "primary" quality: richest metadata wins.
    def quality(r: ScholarlyRecord) -> tuple:
        return (
            bool(r.doi),
            bool(r.abstract),
            len(r.authors),
            len(r.title or ""),
            bool(r.year),
        )

    ordered = sorted(group, key=quality, reverse=True)
    primary = ordered[0]

    sources = []
    for r in group:
        if r.source not in sources:
            sources.append(r.source)
    if any(r.arxiv_id for r in group) and not primary.arxiv_id:
        primary.arxiv_id = next(r.arxiv_id for r in group if r.arxiv_id)

    # fill gaps from siblings, never overwrite good values
    for r in ordered[1:]:
        primary.abstract = primary.abstract or r.abstract
        primary.doi = primary.doi or r.doi
        primary.year = primary.year or r.year
        primary.venue = primary.venue or r.venue
        primary.url = primary.url or r.url
        primary.pdf_url = primary.pdf_url or r.pdf_url
        primary.cited_by = primary.cited_by if primary.cited_by is not None else r.cited_by
        primary.arxiv_id = primary.arxiv_id or r.arxiv_id
        if len(primary.authors) < len(r.authors):
            primary.authors = r.authors
        primary.warnings = sorted(set(primary.warnings) | set(r.warnings))

    if len(sources) > 1:
        if all(r.doi for r in group):
            merge_reasons["doi"] += 1
        elif any(r.arxiv_id for r in group):
            merge_reasons["arxiv"] += 1
        else:
            merge_reasons["title"] += 1

    primary.raw = dict(primary.raw or {})
    primary.raw["merged_sources"] = sources
    primary.raw["source_queries"] = {r.source: r.source_query for r in group if r.source_query}
    primary.source = "+".join(sources)
    return primary
