"""arXiv adapter (Atom feed over the export API)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from app.config import settings
from app.services.scholarly.http import FetchResult, scholar_http
from app.services.scholarly.records import ScholarlyRecord, clean_text, normalize_doi

NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _clean_query(query: str) -> str:
    """arXiv's query language needs explicit boolean syntax."""
    q = re.sub(r"[^\w\s\-]", " ", query).strip()
    terms = [t for t in q.split() if t]
    if not terms:
        return "all:research"
    if len(terms) == 1:
        return f"all:{terms[0]}"
    # OR between all terms gives better recall than implicit AND on arXiv
    return " OR ".join(f"all:{t}" for t in terms[:8])


def _to_record(entry: ET.Element, query: str) -> ScholarlyRecord | None:
    title_el = entry.find("a:title", NS)
    title = clean_text(title_el.text if title_el is not None else None)
    if not title:
        return None
    authors = []
    for a in entry.findall("a:author", NS):
        name_el = a.find("a:name", NS)
        if name_el is not None and name_el.text:
            aff_el = a.find("arxiv:affiliation", NS)
            authors.append(
                {
                    "name": clean_text(name_el.text),
                    "affiliation": clean_text(aff_el.text) if aff_el is not None else None,
                }
            )
    id_el = entry.find("a:id", NS)
    abs_url = clean_text(id_el.text) if id_el is not None else None
    arxiv_id = None
    if abs_url:
        m = re.search(r"/abs/([^v]+)(v\d+)?$", abs_url)
        arxiv_id = m.group(1) if m else None
    published = entry.find("a:published", NS)
    year = None
    if published is not None and published.text:
        m = re.match(r"(\d{4})", published.text)
        year = int(m.group(1)) if m else None
    pdf_url = None
    for link in entry.findall("a:link", NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")
    doi_el = entry.find("arxiv:doi", NS)
    doi = normalize_doi(doi_el.text if doi_el is not None else None)
    summary_el = entry.find("a:summary", NS)
    abstract = clean_text(summary_el.text if summary_el is not None else None)
    cats = [c.get("term") for c in entry.findall("a:category", NS) if c.get("term")]
    comment_el = entry.find("arxiv:comment", NS)
    warnings = ["preprint — not peer-reviewed"] if True else []
    if not doi:
        warnings.append("no DOI (arXiv preprint)")
    return ScholarlyRecord(
        source="arxiv",
        source_query=query,
        title=title,
        doi=doi,
        arxiv_id=arxiv_id,
        authors=authors,
        year=year,
        venue=(f"arXiv {'/'.join(cats[:2])}" if cats else "arXiv"),
        abstract=abstract,
        url=abs_url,
        pdf_url=pdf_url,
        cited_by=None,
        type="preprint",
        open_access=True,
        raw={"categories": cats, "comment": clean_text(comment_el.text) if comment_el is not None else None},
        warnings=warnings,
    )


async def search(
    query: str,
    limit: int = 20,
    year_from: int | None = None,
    year_to: int | None = None,
    types: list[str] | None = None,
) -> tuple[list[ScholarlyRecord], FetchResult]:
    params: dict[str, Any] = {
        "search_query": _clean_query(query),
        "start": 0,
        "max_results": min(max(limit, 1), 50),
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    raw = await scholar_http.get_raw(
        source="arxiv", url=f"{settings.arxiv_base_url}/query", params=params
    )
    if raw.status != "ok" or not raw.payload:
        return [], raw
    try:
        root = ET.fromstring(raw.payload)
    except ET.ParseError as exc:
        raw.status = "error"
        raw.error = f"arXiv returned unparsable XML: {exc}"
        return [], raw
    records = [r for r in (_to_record(e, query) for e in root.findall("a:entry", NS)) if r]
    if year_from or year_to:
        lo = year_from or 0
        hi = year_to or 9999
        records = [r for r in records if r.year is None or lo <= r.year <= hi]
    return records, raw
