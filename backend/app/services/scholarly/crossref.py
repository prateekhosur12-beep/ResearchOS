"""Crossref adapter (https://api.crossref.org)."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.scholarly.http import FetchResult, scholar_http
from app.services.scholarly.records import ScholarlyRecord, clean_text, normalize_doi


def _year(item: dict[str, Any]) -> int | None:
    for key in ("published", "issued", "published-print", "published-online", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and isinstance(parts[0], int):
            return parts[0]
    return None


def _to_record(item: dict[str, Any], query: str) -> ScholarlyRecord | None:
    titles = item.get("title") or []
    title = clean_text(titles[0]) if titles else None
    if not title:
        return None
    authors = []
    for a in item.get("author") or []:
        name = " ".join(p for p in [a.get("given"), a.get("family")] if p) or a.get("name")
        if not name:
            continue
        affs = a.get("affiliation") or []
        authors.append(
            {
                "name": name,
                "orcid": a.get("ORCID"),
                "affiliation": affs[0].get("name") if affs else None,
            }
        )
    containers = item.get("container-title") or []
    doi = normalize_doi(item.get("DOI"))
    abstract = clean_text(item.get("abstract"))
    warnings = []
    if not abstract:
        warnings.append("abstract not available from Crossref")
    if not doi:
        warnings.append("no DOI in Crossref record")
    links = item.get("link") or []
    pdf = next((l.get("URL") for l in links if (l.get("content-type") or "").startswith("application/pdf")), None)
    return ScholarlyRecord(
        source="crossref",
        source_query=query,
        title=title,
        doi=doi,
        authors=authors,
        year=_year(item),
        venue=containers[0] if containers else item.get("publisher"),
        abstract=abstract,
        url=item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        pdf_url=pdf,
        cited_by=item.get("is-referenced-by-count"),
        type=item.get("type"),
        open_access=None,
        raw={"crossref_score": item.get("score"), "publisher": item.get("publisher")},
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
        filters.append(f"from-pub-date:{year_from}-01-01")
    if year_to:
        filters.append(f"until-pub-date:{year_to}-12-31")
    if types:
        filters.append("type:" + ",".join(types))
    params: dict[str, Any] = {
        "query.bibliographic": query,
        "rows": min(max(limit, 1), 50),
        "mailto": settings.scholarly_contact_email,
        "select": (
            "DOI,title,author,abstract,issued,published,container-title,type,"
            "is-referenced-by-count,URL,link,score,publisher,created"
        ),
    }
    if filters:
        params["filter"] = ",".join(filters)

    data, result = await scholar_http.get_json(
        source="crossref", url=f"{settings.crossref_base_url}/works", params=params
    )
    if data is None:
        return [], result
    items = (data.get("message") or {}).get("items") or []
    records = [r for r in (_to_record(i, query) for i in items) if r]
    return records, result


async def lookup_doi(doi: str) -> tuple[ScholarlyRecord | None, FetchResult]:
    nd = normalize_doi(doi) or doi
    data, result = await scholar_http.get_json(
        source="crossref",
        url=f"{settings.crossref_base_url}/works/{nd}",
        params={"mailto": settings.scholarly_contact_email},
        max_retries=1,
    )
    if not data:
        return None, result
    return _to_record(data.get("message") or {}, query=f"doi:{nd}"), result


async def venue_info(issn: str) -> tuple[dict[str, Any] | None, FetchResult]:
    """Journals endpoint: authoritative venue metadata (publisher, ISSN, title)."""
    data, result = await scholar_http.get_json(
        source="crossref",
        url=f"{settings.crossref_base_url}/journals/{issn}",
        params={"mailto": settings.scholarly_contact_email},
        max_retries=1,
    )
    return ((data or {}).get("message")), result


async def journal_search(query: str, limit: int = 5) -> tuple[list[dict], FetchResult]:
    """Journals registered with Crossref — authoritative title/ISSN/publisher metadata."""
    data, result = await scholar_http.get_json(
        source="crossref",
        url=f"{settings.crossref_base_url}/journals",
        params={
            "query": query,
            "rows": min(max(limit, 1), 10),
            "mailto": settings.scholarly_contact_email,
        },
        max_retries=1,
    )
    if not data:
        return [], result
    return (data.get("message") or {}).get("items") or [], result
