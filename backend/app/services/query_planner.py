"""Scholarly query planning (Lab 1 + Lab 3).

The one rule this module enforces: **a user's research instruction is never a search
query.** OpenAlex, Crossref and arXiv each reject queries over 400 characters, and a
multi-paragraph prompt is not a bibliographic query even when it fits.

So the fields are kept separate end to end:

===============  ==========================================================
research_topic   short, clean title (what the scholar calls the study)
instructions     long-form brief; used by agents, never by search APIs
questions        optional research questions; a *source* of query terms only
search_queries   3–6 short keyword strings; the only thing sent to a source
===============  ==========================================================

Model-proposed queries (Ollama) are validated, trimmed, de-duplicated and length-capped
before dispatch. If the model is unavailable or answers with garbage, deterministic
queries are derived from the topic. If even that fails, the sanitised topic is used —
never an empty string, never the raw instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from pydantic import BaseModel, Field

#: Hard limit imposed by ``SearchInput`` and required by all three source APIs.
MAX_QUERY_CHARS = 400
#: What the planner aims for; short queries retrieve better than maximally long ones.
QUERY_SOFT_CAP = 220
MIN_QUERY_CHARS = 3
MAX_QUERIES = 6
MAX_QUESTION_LEN = 400

#: A topic must stay a title. Anything longer belongs in ``instructions``.
MAX_TOPIC_CHARS = 300
MAX_INSTRUCTIONS_CHARS = 20_000

_INSTRUCTION_MARKERS = (
    "please ",
    "you are",
    "you must",
    "i want you",
    "write a ",
    "generate a ",
    "provide a ",
    "act as",
    "make sure",
    "do not ",
    "requirements:",
    "instructions:",
)

_STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "using",
    "by", "from", "at", "as", "is", "are", "be", "we", "our", "this", "that",
    "these", "those", "it", "its", "based", "toward", "towards", "into", "via",
    "how", "what", "why", "which", "can", "does", "do", "should", "would", "could",
    "between", "among", "under", "over", "about", "study", "research", "paper",
    "review", "analysis", "provide", "include", "need", "also", "such", "than",
}

#: Generic verbs/quantifiers that make a keyword string read like a truncated
#: sentence ("recycling processes recover most"). They are dropped when query
#: terms are extracted from questions and instructions.
_QUERY_FILLER = {
    "used", "use", "uses", "recover", "recovers", "reported", "report", "reports",
    "dominant", "dominate", "main", "major", "most", "least", "key", "best", "top",
    "evaluate", "evaluated", "evaluates", "implement", "implemented", "improve",
    "improved", "measure", "measured", "quantify", "quantified", "apply", "applied",
    "compare", "compared", "assess", "assessed", "identify", "identified", "explore",
    "propose", "proposed", "achieve", "achieved", "remain", "remains", "emerging",
    "current", "existing", "future", "recent", "new", "novel", "various", "different",
    "several", "many", "some", "other", "others", "role", "impact", "work", "works",
}

_LEADING_LABEL = re.compile(
    r"^\s*(?:research\s+)?(?:topic|title|subject|project)\s*[:\-–]\s*", re.IGNORECASE
)
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•>]+|\d+[.)])\s*")
_MARKDOWN_PREFIX = re.compile(r"^\s*#{1,6}\s*")
_QUOTES = str.maketrans({'"': "", "'": "", "`": "", "“": "", "”": "", "‘": "", "’": ""})


class QueryPlanOut(BaseModel):
    """Structured output requested from the model."""

    intent: str = ""
    keywords: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    subtopics: list[str] = Field(default_factory=list)


@dataclass
class QueryPlan:
    topic: str
    queries: list[str]
    keywords: list[str] = field(default_factory=list)
    intent: str = ""
    subtopics: list[str] = field(default_factory=list)
    generated_by: str = "heuristic"  # ollama | heuristic | fallback
    warnings: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    used_instructions: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "queries": self.queries,
            "keywords": self.keywords,
            "intent": self.intent,
            "subtopics": self.subtopics,
            "generated_by": self.generated_by,
            "warnings": self.warnings,
            "rejected": self.rejected,
            "used_instructions": self.used_instructions,
            "max_query_chars": MAX_QUERY_CHARS,
        }


# --------------------------------------------------------------------------- text
def collapse(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split())


def sanitize_topic(raw: str) -> str:
    """Reduce any user input to a short, clean research title.

    A pasted brief ("Title: …\\n\\nResearch questions:\\n1. …") must not become the
    topic. We keep the first meaningful line, drop labels/bullets/quotes, and cut at
    a word boundary if it is still long.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    # first non-empty line wins: briefs are usually "Title: X" followed by sections
    for line in text.splitlines():
        candidate = _MARKDOWN_PREFIX.sub("", _BULLET_PREFIX.sub("", line.strip()))
        candidate = _LEADING_LABEL.sub("", candidate).strip()
        if len(candidate) >= MIN_QUERY_CHARS:
            text = candidate
            break
    text = collapse(text.translate(_QUOTES)).strip(" .,;:-–—")
    if len(text) > MAX_TOPIC_CHARS:
        cut = text[:MAX_TOPIC_CHARS]
        if " " in cut:
            cut = cut[: cut.rfind(" ")]
        text = cut.rstrip(" ,;:-–—")
    return text


def looks_like_instruction(text: str) -> bool:
    """True when a string is a brief rather than a search query."""
    low = collapse(text).lower()
    if len(low) > QUERY_SOFT_CAP * 2:
        return True
    if "\n" in (text or "").strip():
        return True
    if low.count(" ") > 45:
        return True
    return any(marker in low for marker in _INSTRUCTION_MARKERS)


def normalize_query(raw: str) -> str | None:
    """Return a dispatch-ready query, or ``None`` if the string cannot be one."""
    if raw is None:
        return None
    text = str(raw)
    if looks_like_instruction(text):
        return None
    text = _MARKDOWN_PREFIX.sub("", _BULLET_PREFIX.sub("", text.strip()))
    text = _LEADING_LABEL.sub("", text)
    text = collapse(text.translate(_QUOTES)).strip(" .,;:!?-–—\"'")
    if len(text) < MIN_QUERY_CHARS:
        return None
    if len(text) > MAX_QUERY_CHARS:  # defensive: never dispatch what a source will reject
        cut = text[:QUERY_SOFT_CAP]
        text = cut[: cut.rfind(" ")].strip() if " " in cut else cut
    if len(text) > MAX_QUERY_CHARS or len(text) < MIN_QUERY_CHARS:
        return None
    return text


def dedupe_queries(queries: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = re.sub(r"[^a-z0-9 ]", "", q.lower())
        key = collapse(key)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def validate_queries(candidates: Iterable[str], limit: int = MAX_QUERIES) -> tuple[list[str], list[str]]:
    """Normalise, validate, de-duplicate and cap a candidate list."""
    good: list[str] = []
    rejected: list[str] = []
    for raw in candidates:
        cleaned = normalize_query(raw)
        if cleaned is None:
            if str(raw).strip():
                rejected.append(collapse(str(raw))[:120])
            continue
        good.append(cleaned)
    good = dedupe_queries(good)[:limit]
    return good, rejected


# ---------------------------------------------------------------------- keywords
def keywords_of(text: str, limit: int = 10) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]+", collapse(text).lower())
    out: list[str] = []
    for tok in tokens:
        if tok in _STOPWORDS or tok in _QUERY_FILLER or len(tok) < 3:
            continue
        if tok not in out:
            out.append(tok)
    return out[:limit]


def normalize_questions(value: Any) -> list[str]:
    """Accept a list or a free-text block and return clean question strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p for p in re.split(r"\n+|(?<=\?)\s+", value) if p.strip()]
    else:
        parts = [str(v) for v in value]
    out: list[str] = []
    for p in parts:
        text = collapse(_BULLET_PREFIX.sub("", p.strip()))
        text = _LEADING_LABEL.sub("", text)
        if len(text) < MIN_QUERY_CHARS:
            continue
        out.append(text[:MAX_QUESTION_LEN])
    return out[:20]


# ---------------------------------------------------------------------- fallback
def heuristic_queries(
    topic: str, questions: list[str] | None = None, instructions: str = "", limit: int = 5
) -> list[str]:
    """Deterministic, conservative queries derived from the topic (and questions).

    No method words are invented: every query is built from words the user actually
    used, so a hit is genuinely about their topic.
    """
    clean_topic = sanitize_topic(topic)
    kw = keywords_of(clean_topic, limit=8)
    candidates: list[str] = []

    if clean_topic:
        candidates.append(clean_topic)
    if len(kw) >= 2:
        candidates.append(" ".join(kw[:2]))
    if len(kw) >= 4:
        candidates.append(" ".join(kw[:4]))
    if len(kw) >= 5:
        # a middle window usually names the technique/object pairs, e.g.
        # "recycling second-life energy" from a title about battery recycling
        candidates.append(" ".join(kw[2:5]))
    elif len(kw) >= 3:
        candidates.append(" ".join(kw[-2:]) + " " + kw[0])
    for q in (questions or [])[:2]:
        qkw = keywords_of(q, limit=6)
        if len(qkw) >= 2:
            candidates.append(" ".join(qkw[:3]))
            if len(qkw) >= 4:
                candidates.append(" ".join(qkw[:2] + qkw[3:5]))
    if instructions:
        ikw = keywords_of(instructions, limit=12)
        if len(ikw) >= 3:
            candidates.append(" ".join(ikw[:3]))
    if clean_topic:
        candidates.append(f"{clean_topic} survey")

    good, _ = validate_queries(candidates, limit=max(1, min(limit, MAX_QUERIES)))
    return good


# ---------------------------------------------------------------------- planning
PLAN_SYSTEM = (
    "You are a research librarian. Convert a research brief into short bibliographic "
    "search queries for OpenAlex, Crossref and arXiv. Hard rules: each query is FEWER "
    "THAN 400 CHARACTERS (aim for 3-8 words), plain keywords only, no boolean operators, "
    "no quotes, no sentence-long strings, no instructions, and every query targets a "
    "different facet of the topic. Return JSON only."
)


async def plan_queries(
    *,
    topic: str,
    instructions: str = "",
    questions: list[str] | None = None,
    domain: str = "computer_science",
    llm: Any = None,
    max_queries: int = 5,
) -> QueryPlan:
    """Produce validated search queries. Never returns the raw instruction."""
    clean_topic = sanitize_topic(topic)
    questions = questions or []
    if not clean_topic:
        # last-ditch: derive a topic from the brief instead of sending nothing
        clean_topic = sanitize_topic(instructions) or "research"
    max_queries = max(1, min(max_queries, MAX_QUERIES))

    candidates: list[str] = []
    rejected: list[str] = []
    generated_by = "heuristic"
    intent = f"Retrieve scholarly work about {clean_topic}"
    keywords: list[str] = keywords_of(clean_topic)
    subtopics: list[str] = []
    warnings: list[str] = []
    used_instructions = bool(instructions or questions)

    if llm is not None:
        health = await llm.health()
        if health.get("available"):
            brief = clean_topic
            if questions:
                brief += "\nResearch questions:\n" + "\n".join(f"- {q}" for q in questions[:6])
            if instructions:
                brief += "\nBrief (context only — do NOT copy it into a query):\n" + instructions[:1500]
            res = await llm.chat_structured(
                [
                    {"role": "system", "content": PLAN_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Research topic: {clean_topic}\nDomain: {domain}\n\n{brief}\n\n"
                            'Return JSON: {"intent":"one sentence","keywords":[5-8 terms],'
                            '"queries":[3-6 search queries, 3-8 words each, <400 chars],'
                            '"subtopics":[3-5 facets]}'
                        ),
                    },
                ],
                QueryPlanOut,
                temperature=0.2,
                num_predict=400,
            )
            if res.ok and res.data:
                model_queries, model_rejected = validate_queries(res.data.queries, limit=max_queries)
                rejected.extend(model_rejected)
                if model_queries:
                    candidates.extend(model_queries)
                    generated_by = "ollama"
                    intent = collapse(res.data.intent) or intent
                    keywords = [k for k in (collapse(x) for x in res.data.keywords) if k][:10] or keywords
                    subtopics = [collapse(x) for x in res.data.subtopics][:5]
                else:
                    warnings.append(
                        "The model returned no usable search query (empty, too long or "
                        "instruction-shaped); deterministic queries were used instead."
                    )
            else:
                warnings.append(f"Query planning model call failed: {res.error}")
        else:
            warnings.append(
                f"LLM unavailable ({health.get('detail', '')}); queries derived deterministically."
            )
    else:
        warnings.append("LLM not consulted; queries derived deterministically.")

    # Always keep deterministic coverage: the model proposes, the planner disposes.
    fallback = heuristic_queries(clean_topic, questions, instructions, limit=max_queries)
    candidates.extend(fallback)

    queries, more_rejected = validate_queries(candidates, limit=max_queries)
    rejected.extend(more_rejected)

    if not queries:
        queries = [clean_topic[:QUERY_SOFT_CAP]]
        generated_by = "fallback"
        warnings.append("No candidate query survived validation; used the cleaned topic itself.")

    return QueryPlan(
        topic=clean_topic,
        queries=queries,
        keywords=keywords,
        intent=intent,
        subtopics=subtopics,
        generated_by=generated_by,
        warnings=warnings,
        rejected=rejected,
        used_instructions=used_instructions,
    )
