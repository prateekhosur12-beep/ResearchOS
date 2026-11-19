"""CitationFormatSkill — deterministic reference formatting (Lab 3).

Pure function of the supplied metadata: no model, no network, no invention.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.skills.base import Skill, SkillResult


class CitationEntry(BaseModel):
    key: str = ""
    paper_id: str = ""
    title: str
    authors: list[dict[str, Any]] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    volume: str | None = None
    pages: str | None = None


class CitationFormatInput(BaseModel):
    style: Literal["APA", "IEEE", "BibTeX", "plain"] = "IEEE"
    entries: list[CitationEntry]


class CitationFormatOutput(BaseModel):
    style: str
    formatted: list[dict[str, Any]]
    note: str


def _surname(author: dict[str, Any]) -> str:
    name = (author.get("name") or "").strip()
    if not name:
        return ""
    if "," in name:
        return name.split(",")[0].strip()
    return name.split()[-1]


def _initials(author: dict[str, Any]) -> str:
    name = (author.get("name") or "").strip()
    if not name:
        return ""
    if "," in name:
        given = name.split(",", 1)[1].strip()
    else:
        parts = name.split()
        given = " ".join(parts[:-1])
    return " ".join(f"{p[0]}." for p in given.split() if p)


def _apa(entries: list[CitationEntry]) -> list[str]:
    out = []
    for e in entries:
        authors = [_surname(a) for a in e.authors if _surname(a)]
        if not authors:
            auth = "Anon."
        elif len(authors) == 1:
            auth = f"{authors[0]}, {_initials(e.authors[0])}"
        elif len(authors) <= 20:
            head = ", ".join(f"{_surname(a)}, {_initials(a)}" for a in e.authors[:-1])
            auth = f"{head}, & {authors[-1]}, {_initials(e.authors[-1])}"
        else:
            auth = f"{authors[0]}, {_initials(e.authors[0])}, et al."
        year = f"({e.year})." if e.year else "(n.d.)."
        venue = f" *{e.venue}*." if e.venue else ""
        doi = f" https://doi.org/{e.doi}" if e.doi else (f" {e.url}" if e.url else "")
        out.append(f"{auth} {year} {e.title}.{venue}{doi}".replace("..", "."))
    return out


def _ieee(entries: list[CitationEntry]) -> list[str]:
    out = []
    for i, e in enumerate(entries, 1):
        authors = []
        for a in e.authors[:6]:
            s, ini = _surname(a), _initials(a)
            if s:
                authors.append(f"{ini} {s}")
        if not authors:
            auth = "Anon."
        elif len(e.authors) > 6:
            auth = ", ".join(authors) + ", et al."
        else:
            auth = ", ".join(authors)
        venue = f"*{e.venue}*" if e.venue else ""
        year = e.year or "n.d."
        tail = f", doi: {e.doi}." if e.doi else (f", {e.url}." if e.url else ".")
        out.append(f"[{i}] {auth}, \"{e.title},\" {venue}, {year}{tail}".replace(" ,", ",").replace("  ", " "))
    return out


def _bibtex(entries: list[CitationEntry]) -> list[str]:
    out = []
    for e in entries:
        first = _surname(e.authors[0]).lower() if e.authors else "anon"
        key = e.key or f"{re.sub(r'[^a-z]', '', first)}{e.year or 'nd'}"
        authors = " and ".join(
            f"{_surname(a)}, {_initials(a)}".strip(", ") for a in e.authors if _surname(a)
        )
        fields = [
            f"  title = {{{e.title}}}",
            f"  author = {{{authors}}}" if authors else None,
            f"  year = {{{e.year}}}" if e.year else None,
            f"  journal = {{{e.venue}}}" if e.venue else None,
            f"  doi = {{{e.doi}}}" if e.doi else None,
            f"  url = {{{e.url}}}" if e.url else None,
        ]
        body = ",\n".join(f for f in fields if f)
        out.append(f"@article{{{key},\n{body}\n}}")
    return out


def _plain(entries: list[CitationEntry]) -> list[str]:
    out = []
    for e in entries:
        names = ", ".join(a.get("name", "") for a in e.authors[:4]) or "Unknown authors"
        if len(e.authors) > 4:
            names += ", et al."
        ident = f"doi:{e.doi}" if e.doi else (e.url or "no identifier")
        out.append(f"{names} ({e.year or 'n.d.'}). {e.title}. {e.venue or ''} {ident}".strip())
    return out


FORMATTERS = {"APA": _apa, "IEEE": _ieee, "BibTeX": _bibtex, "plain": _plain}


class CitationFormatSkill(Skill):
    name = "CitationFormatSkill"
    description = "Format reference entries as APA, IEEE or BibTeX from stored metadata."
    instructions = "Deterministic formatting. Missing metadata is omitted, never fabricated."
    input_schema = CitationFormatInput
    output_schema = CitationFormatOutput

    async def run(self, payload: dict[str, Any]) -> SkillResult:
        data = self.validate_input(payload)
        entries = [CitationEntry.model_validate(e) for e in data["entries"]]
        style = data["style"]
        formatted = FORMATTERS[style](entries)
        warnings = []
        for e in entries:
            if not e.authors:
                warnings.append(f"'{e.title[:60]}' has no author metadata in the source record")
            if not e.year:
                warnings.append(f"'{e.title[:60]}' has no publication year in the source record")
            if not e.doi:
                warnings.append(f"'{e.title[:60]}' has no DOI (cannot be verified automatically)")
        records = []
        for e, text in zip(entries, formatted):
            records.append(
                {
                    "key": e.key or e.paper_id,
                    "paper_id": e.paper_id,
                    "text": text,
                    "doi": e.doi,
                    "has_authors": bool(e.authors),
                    "has_year": bool(e.year),
                }
            )
        return SkillResult(
            ok=True,
            data=CitationFormatOutput(
                style=style,
                formatted=records,
                note="Rendered from stored metadata only; unverified fields are flagged.",
            ).model_dump(),
            generated_by="deterministic",
            warnings=sorted(set(warnings))[:20],
        )
