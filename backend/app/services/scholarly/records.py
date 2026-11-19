"""Normalized scholarly record + text utilities shared by all adapters."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


def normalize_title(title: str) -> str:
    """Fold case, strip punctuation/whitespace so near-identical titles collapse."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"<[^>]+>", " ", t)          # strip html tags
    t = re.sub(r"[^a-z0-9 ]+", " ", t)       # punctuation -> space
    t = re.sub(r"\s+", " ", t).strip()
    return t[:280]


def clean_text(text: str | None) -> str | None:
    if not text:
        return None
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"\s+", " ", t).strip()
    return t or None


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://dx.doi.org/"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
    d = d.strip().rstrip(".").lower()
    return d if re.match(r"^10\.\d{4,9}/\S+$", d) else None


def reconstruct_openalex_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as {word: [positions]}. Many records have none."""
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return clean_text(" ".join(w for _, w in positions))


def arxiv_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", url)
    return m.group(1) if m else None


@dataclass
class ScholarlyRecord:
    source: str
    title: str
    source_query: str = ""
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[dict[str, Any]] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    cited_by: int | None = None
    type: str | None = None
    open_access: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def norm_title(self) -> str:
        return normalize_title(self.title)

    @property
    def dedupe_key(self) -> str:
        """Stable identity: DOI > arXiv id > normalized title."""
        if self.doi:
            return f"doi:{self.doi}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        return f"title:{self.norm_title}"

    def secondary_keys(self) -> set[str]:
        keys: set[str] = set()
        if self.doi:
            keys.add(f"doi:{self.doi}")
        if self.arxiv_id:
            keys.add(f"arxiv:{self.arxiv_id}")
        if self.norm_title:
            keys.add(f"title:{self.norm_title}")
        return keys

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "authors": self.authors,
            "year": self.year,
            "venue": self.venue,
            "abstract": self.abstract,
            "url": self.url,
            "pdf_url": self.pdf_url,
            "cited_by": self.cited_by,
            "type": self.type,
            "open_access": self.open_access,
            "warnings": self.warnings,
        }
