"""Research query generation (Part 1 of the improvement brief).

The bug being locked down: a long research *instruction* used to be handed to the
scholarly APIs as if it were a query, so all three sources rejected it
("String should have at most 400 characters") and nothing was retrieved.
"""

from __future__ import annotations

import pytest

from app.schemas.models import ProjectCreate
from app.services.query_planner import (
    MAX_QUERY_CHARS,
    heuristic_queries,
    normalize_query,
    normalize_questions,
    plan_queries,
    sanitize_topic,
    validate_queries,
)

LONG_BRIEF = """
AI-Driven Precision Agriculture: Predicting Crop Yield and Optimizing Irrigation Under Climate Change

Research topic
I want you to investigate how artificial intelligence can improve precision agriculture.
Please write a full literature review, a gap analysis, three research ideas and a report.

Research questions
1. Which machine-learning models best predict crop yield from remote sensing?
2. How can irrigation scheduling be optimised under climate change?
3. What datasets are available for Indian agro-climatic zones?

Requirements
- Provide a literature review with at least twenty references.
- Include a research gap analysis and citation audit.
- Generate a complete report with sections.
"""


def test_topic_is_separated_from_the_brief():
    """The title stays a title; the brief never becomes the topic."""
    project = ProjectCreate(
        topic="AI-Driven Precision Agriculture: Predicting Crop Yield and Optimizing Irrigation",
        research_instructions=LONG_BRIEF,
        research_questions="1. Which models predict yield?\n2. How to optimise irrigation?",
    )
    assert len(project.topic) < 120
    assert "\n" not in project.topic
    assert project.topic in LONG_BRIEF  # taken from the brief, not invented
    assert len(project.research_instructions) > 500
    assert project.research_questions == [
        "Which models predict yield?",
        "How to optimise irrigation?",
    ]


def test_overlong_topic_is_rejected_with_guidance():
    with pytest.raises(Exception) as excinfo:
        ProjectCreate(topic=LONG_BRIEF)
    message = str(excinfo.value)
    assert "research_instructions" in message
    assert "300" in message


def test_sanitize_topic_handles_prompt_scaffolding():
    assert sanitize_topic("Title: Blockchain-Based Digital Identity") == "Blockchain-Based Digital Identity"
    assert sanitize_topic("## Topic: Battery Recycling\n\nmore text") == "Battery Recycling"
    assert sanitize_topic("- Crop yield prediction with satellites") == "Crop yield prediction with satellites"
    assert len(sanitize_topic("word " * 200)) <= 300


def test_instruction_shaped_strings_are_never_queries():
    assert normalize_query(LONG_BRIEF) is None
    assert normalize_query("Please write a full literature review") is None
    assert normalize_query("You must include twenty references") is None
    assert normalize_query("AI-based crop yield prediction") == "AI-based crop yield prediction"


def test_every_query_is_under_the_api_limit_and_deduplicated():
    candidates = [
        "crop yield prediction",
        "Crop Yield Prediction",           # duplicate, different case
        "  crop   yield prediction  ",     # duplicate after whitespace collapse
        "x" * 900,                         # way over the limit
        "ab",                              # too short
        "",
    ]
    good, rejected = validate_queries(candidates)
    assert good == ["crop yield prediction"]
    # the oversized and the too-short candidate are reported; empty strings are
    # simply ignored rather than reported as user error
    assert len(rejected) == 2
    assert all(len(q) <= MAX_QUERY_CHARS for q in good)


@pytest.mark.asyncio
async def test_planner_never_sends_the_brief_without_an_llm():
    """No Ollama: deterministic queries, still short, still topic-specific."""
    plan = await plan_queries(
        topic="AI-Driven Precision Agriculture: Predicting Crop Yield",
        instructions=LONG_BRIEF,
        questions=["Which models predict crop yield from remote sensing?"],
        llm=None,
    )
    assert 3 <= len(plan.queries) <= 6
    assert all(len(q) <= MAX_QUERY_CHARS for q in plan.queries)
    assert all(q not in plan.queries[:i] for i, q in enumerate(plan.queries))
    assert plan.generated_by in ("heuristic", "fallback")
    assert any("deterministically" in w for w in plan.warnings)
    # none of the dispatched queries carries the instruction body
    for q in plan.queries:
        assert "Requirements" not in q and "\n" not in q
        assert "literature review" not in q.lower()
        assert len(q.split()) <= 12


@pytest.mark.asyncio
async def test_llm_proposals_are_validated_and_repaired(fake_ollama):
    fake_ollama["chat"] = {
        "intent": "Predict crop yield with AI",
        "keywords": ["crop yield", "precision agriculture", "irrigation"],
        "queries": [
            "AI-based crop yield prediction",
            "deep learning for precision agriculture",
            LONG_BRIEF.strip()[:600],          # must be rejected: instruction + too long
            "satellite imagery for crop monitoring",
            "satellite imagery for crop monitoring",  # duplicate
        ],
        "subtopics": ["remote sensing", "irrigation scheduling"],
    }
    plan = await plan_queries(
        topic="AI-Driven Precision Agriculture: Predicting Crop Yield",
        instructions=LONG_BRIEF,
        llm=__import__("app.services.llm", fromlist=["get_llm"]).get_llm(),
    )
    assert plan.generated_by == "ollama"
    assert "AI-based crop yield prediction" in plan.queries
    assert len([q for q in plan.queries if "satellite imagery" in q]) == 1
    assert all(len(q) <= MAX_QUERY_CHARS for q in plan.queries)
    assert plan.rejected, "the oversized instruction-shaped proposal must be reported"


@pytest.mark.asyncio
async def test_llm_garbage_falls_back_instead_of_failing(fake_ollama):
    fake_ollama["chat"] = {"intent": "", "keywords": [], "queries": [LONG_BRIEF[:400]], "subtopics": []}
    plan = await plan_queries(
        topic="Sustainable Battery Recycling and Second-Life Energy Storage",
        instructions=LONG_BRIEF,
        llm=__import__("app.services.llm", fromlist=["get_llm"]).get_llm(),
    )
    assert plan.queries, "must never return an empty query list"
    assert all(len(q) <= MAX_QUERY_CHARS for q in plan.queries)
    assert any("no usable search query" in w for w in plan.warnings)


@pytest.mark.asyncio
async def test_topic_only_input_still_produces_multiple_queries():
    plan = await plan_queries(topic="graph neural networks for molecular property prediction", llm=None)
    assert len(plan.queries) >= 3
    assert all("graph" in q.lower() or "molecular" in q.lower() for q in plan.queries)


def test_heuristic_queries_stay_close_to_the_users_words():
    queries = heuristic_queries("Blockchain-Based Digital Identity and Privacy-Preserving Authentication")
    assert queries
    assert queries[0] == "Blockchain-Based Digital Identity and Privacy-Preserving Authentication"
    assert all(len(q) <= MAX_QUERY_CHARS for q in queries)


def test_normalize_questions_accepts_text_and_lists():
    assert normalize_questions("1. How accurate?\n2. What data?") == ["How accurate?", "What data?"]
    assert normalize_questions(["What works?"]) == ["What works?"]
    assert normalize_questions("") == []
    assert len(normalize_questions(["x" * 900])) == 1
    assert len(normalize_questions(["x" * 900])[0]) <= 400
