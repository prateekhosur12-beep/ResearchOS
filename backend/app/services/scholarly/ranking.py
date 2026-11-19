"""Explainable relevance ranking.

Every score is decomposed into named components that the UI can display, so a
ranking is never a mystery number (see PaperOut.rank_explain).
"""

from __future__ import annotations

import datetime as dt
import math
import re

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "in", "on", "with", "to", "using", "via",
    "based", "toward", "towards", "from", "by", "at", "as", "is", "are", "be", "this",
    "that", "these", "those", "we", "our", "its", "it", "study", "paper", "approach",
    "method", "methods", "analysis", "review", "novel", "new", "research", "system",
}

SYNONYMS = {
    "ai": {"artificial", "intelligence"},
    "ml": {"machine", "learning"},
    "dl": {"deep", "learning"},
    "llm": {"large", "language", "model"},
    "llms": {"large", "language", "model"},
    "iot": {"internet", "things"},
    "rag": {"retrieval", "augmented", "generation"},
    "cv": {"computer", "vision"},
    "nlp": {"natural", "language", "processing"},
    "xai": {"explainable"},
}


def tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    raw = re.findall(r"[a-z0-9][a-z0-9\-]+", text.lower())
    out: list[str] = []
    for tok in raw:
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        out.append(tok)
        for syn in SYNONYMS.get(tok, ()):  # acronym expansion
            out.append(syn)
    return out


def _stem_light(tok: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "ers", "er", "es", "s"):
        if len(tok) > 5 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def build_topic_terms(*texts: str) -> set[str]:
    terms: set[str] = set()
    for t in texts:
        terms.update(_stem_light(tok) for tok in tokenize(t))
    return terms


def overlap_score(terms: set[str], title: str | None, abstract: str | None) -> dict:
    title_terms = {_stem_light(t) for t in tokenize(title)}
    abs_terms = {_stem_light(t) for t in tokenize(abstract)}
    if not terms:
        return {"title_overlap": 0.0, "abstract_overlap": 0.0, "matched_terms": []}
    title_hits = terms & title_terms
    abs_hits = terms & abs_terms
    title_cov = len(title_hits) / len(terms)
    abs_cov = len(abs_hits) / len(terms)
    combined = 0.6 * title_cov + 0.4 * abs_cov
    return {
        "title_overlap": round(title_cov, 4),
        "abstract_overlap": round(abs_cov, 4),
        "matched_terms": sorted(title_hits | abs_hits)[:12],
        "score": round(min(1.0, combined * 1.6), 4),  # coverage rarely hits 1.0
    }


def recency_score(year: int | None, current_year: int | None = None, half_life: float = 6.0) -> float:
    if not year:
        return 0.25  # unknown year: neutral-low, never fabricated
    cy = current_year or dt.date.today().year
    age = max(0, cy - year)
    return round(math.exp(-age / half_life), 4)


def citation_score(cited_by: int | None) -> float:
    if cited_by is None:
        return 0.0
    if cited_by <= 0:
        return 0.05
    return round(min(1.0, math.log1p(cited_by) / math.log1p(1500)), 4)


def source_agreement_score(sources: list[str]) -> float:
    n = len(set(sources))
    if n <= 1:
        return 0.0
    return round(min(1.0, (n - 1) / 2), 4)


def explain_ranking(
    *,
    topic: str,
    queries: list[str],
    title: str,
    abstract: str | None,
    year: int | None,
    cited_by: int | None,
    sources: list[str],
) -> dict:
    """Weighted, explainable composite. Weights are fixed and documented."""
    terms = build_topic_terms(topic, *queries)
    ov = overlap_score(terms, title, abstract)
    comp = {
        "topic_overlap": ov["score"],
        "title_overlap": ov["title_overlap"],
        "abstract_overlap": ov["abstract_overlap"],
        "recency": recency_score(year),
        "citation_impact": citation_score(cited_by),
        "abstract_available": 1.0 if abstract else 0.0,
        "source_agreement": source_agreement_score(sources),
    }
    weights = {
        "topic_overlap": 0.45,
        "recency": 0.18,
        "citation_impact": 0.14,
        "abstract_available": 0.13,
        "source_agreement": 0.10,
    }
    total = sum(comp[k] * w for k, w in weights.items())
    return {
        "score": round(total, 4),
        "components": comp,
        "weights": weights,
        "matched_terms": ov["matched_terms"],
        "notes": [
            "topic_overlap: share of topic/query terms found in title (60%) and abstract (40%)",
            "recency: exponential decay, half-life 6 years",
            "citation_impact: log-scaled cited_by_count (0 if the source reports none)",
            "abstract_available: source supplied an abstract",
            "source_agreement: how many independent sources returned the record",
        ],
    }
