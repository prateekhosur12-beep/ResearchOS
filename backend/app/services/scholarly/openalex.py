"""OpenAlex adapter (https://docs.openalex.org)."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.scholarly.http import FetchResult, scholar_http
from app.services.scholarly.records import (
    ScholarlyRecord,
    clean_text,
    normalize_doi,
    reconstruct_openalex_abstract,
)


def _to_record(item: dict[str, Any], query: str) -> ScholarlyRecord | None:
    title = clean_text(item.get("title") or item.get("display_name"))
    if not title:
        return None
    authors = []
    for a in item.get("authorships") or []:
        author = a.get("author") or {}
        name = author.get("display_name")
        if not name:
            continue
        insts = [i.get("display_name") for i in (a.get("institutions") or []) if i.get("display_name")]
        authors.append(
            {
                "name": name,
                "openalex_id": author.get("id"),
                "orcid": author.get("orcid"),
                "affiliation": insts[0] if insts else None,
            }
        )
    loc = item.get("primary_location") or {}
    src = (loc.get("source") or {}) if isinstance(loc, dict) else {}
    oa = item.get("open_access") or {}
    best = item.get("best_oa_location") or {}
    abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
    warnings = []
    if not abstract:
        warnings.append("abstract not available from OpenAlex")
    return ScholarlyRecord(
        source="openalex",
        source_query=query,
        title=title,
        doi=normalize_doi(item.get("doi")),
        arxiv_id=None,
        authors=authors,
        year=item.get("publication_year"),
        venue=src.get("display_name"),
        abstract=abstract,
        url=item.get("id") or loc.get("landing_page_url"),
        pdf_url=best.get("pdf_url") or oa.get("oa_url"),
        cited_by=item.get("cited_by_count"),
        type=item.get("type"),
        open_access=oa.get("is_oa"),
        raw={"openalex_id": item.get("id"), "relevance_score": item.get("relevance_score")},
        warnings=warnings,
    )


async def search(
    query: str,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    types: list[str] | None = None,
) -> tuple[list[ScholarlyRecord], FetchResult]:
    filters: list[str] = []
    if year_from:
        filters.append(f"from_publication_date:{year_from}-01-01")
    if year_to:
        filters.append(f"to_publication_date:{year_to}-12-31")
    if types:
        filters.append("type:" + "|".join(types))
    params: dict[str, Any] = {
        "search": query,
        "per-page": min(max(limit, 1), 50),
        "mailto": settings.scholarly_contact_email,
        "sort": "relevance_score:desc",
    }
    if filters:
        params["filter"] = ",".join(filters)

    data, result = await scholar_http.get_json(
        source="openalex", url=f"{settings.openalex_base_url}/works", params=params
    )
    if data is None:
        return [], result
    records = [r for r in (_to_record(i, query) for i in data.get("results") or []) if r]
    return records, result


async def lookup_doi(doi: str) -> tuple[ScholarlyRecord | None, FetchResult]:
    from app.services.scholarly.records import normalize_doi

    nd = normalize_doi(doi) or doi
    data, result = await scholar_http.get_json(
        source="openalex",
        url=f"{settings.openalex_base_url}/works/https://doi.org/{nd}",
        params={"mailto": settings.scholarly_contact_email},
        max_retries=1,
    )
    if not data:
        return None, result
    return _to_record(data, query=f"doi:{nd}"), result


async def author_works(author_id: str, limit: int = 10) -> tuple[list[ScholarlyRecord], FetchResult]:
    aid = author_id.rsplit("/", 1)[-1] if "/" in author_id else author_id
    data, result = await scholar_http.get_json(
        source="openalex",
        url=f"{settings.openalex_base_url}/works",
        params={
            "filter": f"author.id:{aid}",
            "per-page": min(limit, 50),
            "sort": "cited_by_count:desc",
            "mailto": settings.scholarly_contact_email,
        },
    )
    if not data:
        return [], result
    return [r for r in (_to_record(i, query=f"author:{aid}") for i in data.get("results") or []) if r], result


async def funders_search(query: str, limit: int = 10) -> tuple[list[dict], FetchResult]:
    """Funder lookup. Returns OpenAlex-verified funder entities (not grant calls)."""
    data, result = await scholar_http.get_json(
        source="openalex",
        url=f"{settings.openalex_base_url}/funders",
        params={
            "search": query,
            "per-page": min(max(limit, 1), 25),
            "mailto": settings.scholarly_contact_email,
        },
        max_retries=1,
    )
    if not data:
        return [], result
    return data.get("results") or [], result


async def works_with_funders(
    query: str, limit: int = 25
) -> tuple[list[dict], FetchResult]:
    """Works plus their funder/award metadata (OpenAlex 'awards' + 'funders')."""
    data, result = await scholar_http.get_json(
        source="openalex",
        url=f"{settings.openalex_base_url}/works",
        params={
            "search": query,
            "per-page": min(max(limit, 1), 50),
            "mailto": settings.scholarly_contact_email,
        },
    )
    if not data:
        return [], result
    return data.get("results") or [], result


async def author_profile(author_id: str) -> tuple[dict | None, FetchResult]:
    aid = author_id.rsplit("/", 1)[-1] if "/" in author_id else author_id
    data, result = await scholar_http.get_json(
        source="openalex",
        url=f"{settings.openalex_base_url}/authors/{aid}",
        params={"mailto": settings.scholarly_contact_email},
        max_retries=1,
    )
    return data, result
