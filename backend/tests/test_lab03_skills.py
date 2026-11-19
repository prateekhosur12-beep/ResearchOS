"""Lab 3 — Reusable skills: schemas, validation, LLM and deterministic paths."""

from __future__ import annotations

import pytest

from app.skills.citation_format import CitationFormatSkill
from app.skills.gap_matrix import GapMatrixSkill
from app.skills.literature_summarizer import LiteratureSummarizerSkill
from app.skills.manuscript_section import ManuscriptSectionSkill
from app.skills.research_question import ResearchQuestionSkill

PAPERS = [
    {
        "id": "p1",
        "title": "YOLO based road anomaly detection for Indian roads",
        "abstract": "We propose a YOLO detector for potholes. A limitation is the lack of cross-city "
        "generalisation. Future work will address real-time deployment on edge devices.",
        "year": 2024,
        "venue": "CV Journal",
        "doi": "10.1000/a",
        "url": "https://example.org/a",
        "sources": ["crossref"],
    },
    {
        "id": "p2",
        "title": "Transformer based anomaly detection benchmark",
        "abstract": "We benchmark transformers on Road Anomaly benchmarks. However this approach "
        "remains challenging on embedded hardware.",
        "year": 2025,
        "venue": "Bench Journal",
        "doi": None,
        "url": None,
        "sources": ["openalex"],
    },
    {
        "id": "p3",
        "title": "A survey of anomaly detection",
        "abstract": None,
        "year": 2022,
        "venue": "Survey Journal",
        "doi": None,
        "url": None,
        "sources": ["arxiv"],
    },
]


@pytest.mark.asyncio
async def test_summarizer_fallback_is_labelled_and_grounded():
    skill = LiteratureSummarizerSkill()
    res = await skill.run({"topic": "road anomaly detection", "papers": PAPERS, "domain": "computer_science"})
    assert res.ok
    assert res.generated_by == "heuristic-extraction"
    assert res.llm_used is False
    analyses = res.data["analyses"]
    assert len(analyses) == 3
    first = analyses[0]
    assert "extracted verbatim" in first["basis"]
    assert "RDD2022" not in first["datasets"]  # never invents what the text lacks
    assert first["limitations"]
    # A paper without an abstract is flagged, not filled in
    assert analyses[2]["abstract_available"] is False
    assert analyses[2]["basis"].startswith("abstract unavailable")


@pytest.mark.asyncio
async def test_summarizer_accepts_valid_llm_output(fake_ollama):
    fake_ollama["chat"] = {
        "analyses": [
            {
                "index": 0,
                "research_problem": "pothole detection",
                "methodology": "YOLO",
                "datasets": [],
                "findings": [],
                "limitations": ["cross-city generalisation"],
                "relevance_to_topic": "direct",
            }
        ]
    }
    skill = LiteratureSummarizerSkill()
    res = await skill.run({"topic": "road anomaly detection", "papers": PAPERS[:1]})
    assert res.ok and res.llm_used
    assert res.generated_by.startswith("ollama:")
    assert any("verify against the cited sources" in w for w in res.warnings)


@pytest.mark.asyncio
async def test_summarizer_rejects_out_of_schema_llm_output(fake_ollama):
    fake_ollama["chat"] = {"analyses": [{"index": "not-an-int"}]}
    skill = LiteratureSummarizerSkill()
    res = await skill.run({"topic": "road anomaly detection", "papers": PAPERS[:1]})
    # falls back to deterministic extraction rather than propagating bad data
    assert res.ok
    assert res.generated_by == "heuristic-extraction"
    assert res.error


@pytest.mark.asyncio
async def test_gap_matrix_links_evidence_and_labels_kind(fake_ollama):
    fake_ollama["chat"] = {
        "gaps": [
            {
                "title": "Cross-city generalisation",
                "description": "Models are tuned per city.",
                "rationale": "Two papers flag it.",
                "evidence_indexes": [0],
                "evidence_quotes": [{"index": 0, "quote": "lack of cross-city generalisation"}],
                "kind": "evidence_backed",
                "confidence": 0.7,
                "feasibility": "medium",
                "suggested_metrics": ["mAP"],
            },
            {
                "title": "Ungrounded idea",
                "description": "not supported by any supplied paper",
                "evidence_indexes": [],
                "kind": "hypothesis",
                "confidence": 0.9,
            },
        ]
    }
    skill = GapMatrixSkill()
    res = await skill.run({"topic": "road anomaly detection", "papers": PAPERS, "max_gaps": 6})
    gaps = res.data["gaps"]
    assert [g["title"] for g in gaps] == ["Cross-city generalisation"], "ungrounded gaps must be dropped"
    assert gaps[0]["evidence_paper_ids"] == ["p1"]
    assert gaps[0]["kind"] == "evidence_backed"
    assert gaps[0]["evidence_quotes"][0]["paper_id"] == "p1"
    assert res.data["matrix"][0]["paper_id"] == "p1"


@pytest.mark.asyncio
async def test_heuristic_gap_matrix_without_llm():
    skill = GapMatrixSkill()
    res = await skill.run({"topic": "road anomaly detection", "papers": PAPERS})
    assert res.generated_by == "heuristic-extraction"
    types = {g["kind"] for g in res.data["gaps"]}
    assert "evidence_backed" in types
    for gap in res.data["gaps"]:
        assert gap["evidence_paper_ids"], "no gap may ship without supporting papers"
    assert res.data["coverage"]["papers"] == 3
    assert res.data["coverage"]["with_abstract"] == 2


@pytest.mark.asyncio
async def test_citation_format_skill_styles():
    entries = [
        {
            "key": "P1",
            "paper_id": "p1",
            "title": "YOLO based road anomaly detection",
            "authors": [{"name": "Ada Lovelace"}, {"name": "Alan Turing"}],
            "year": 2024,
            "venue": "CV Journal",
            "doi": "10.1000/a",
        },
        {"key": "P2", "paper_id": "p2", "title": "Untitled record", "authors": [], "year": None},
    ]
    skill = CitationFormatSkill()
    ieee = await skill.run({"style": "IEEE", "entries": entries})
    apa = await skill.run({"style": "APA", "entries": entries})
    bib = await skill.run({"style": "BibTeX", "entries": entries})
    assert ieee.data["formatted"][0]["text"].startswith("[1] A. Lovelace, A. Turing")
    assert "doi: 10.1000/a" in ieee.data["formatted"][0]["text"]
    assert apa.data["formatted"][0]["text"].startswith("Lovelace, A.")
    assert bib.data["formatted"][0]["text"].startswith("@article{")
    assert any("no author metadata" in w for w in ieee.warnings)
    assert any("no publication year" in w for w in ieee.warnings)


@pytest.mark.asyncio
async def test_manuscript_section_strips_invented_citations(fake_ollama):
    fake_ollama["chat"] = {"markdown": "We build on prior work [P1] and also [P99].", "citations": ["P1", "P99"]}
    skill = ManuscriptSectionSkill()
    res = await skill.run(
        {
            "section": "introduction",
            "topic": "road anomaly detection",
            "sources": [{"paper_id": "p1", "key": "P1", "title": "YOLO detector", "year": 2024}],
            "gaps": [],
            "domain": "computer_science",
        }
    )
    assert "[P99]" not in res.data["markdown"]
    assert "[P1]" in res.data["markdown"]
    assert any("not in the bibliography" in w for w in res.warnings)


@pytest.mark.asyncio
async def test_manuscript_section_template_never_claims_results():
    skill = ManuscriptSectionSkill()
    for section in ("abstract", "limitations", "conclusion"):
        res = await skill.run(
            {
                "section": section,
                "topic": "road anomaly detection",
                "sources": [
                    {
                        "paper_id": p["id"],
                        "key": f"P{i + 1}",
                        "title": p["title"],
                        "abstract": p["abstract"],
                        "year": p["year"],
                    }
                    for i, p in enumerate(PAPERS)
                ],
                "gaps": [{"title": "Cross-city generalisation", "description": "x", "kind": "hypothesis",
                          "evidence_paper_ids": ["p1"]}],
                "domain": "computer_science",
            }
        )
        md = res.data["markdown"].lower()
        assert "no experiments" in md or "not achieved" in md or "proposal" in md or section == "limitations"
        assert res.data["word_count"] > 10


@pytest.mark.asyncio
async def test_research_question_skill_produces_proposal():
    skill = ResearchQuestionSkill()
    res = await skill.run(
        {
            "topic": "road anomaly detection",
            "domain": "computer_science",
            "gaps": [
                {
                    "title": "Cross-city generalisation",
                    "description": "Models trained per city.",
                    "evidence_paper_ids": ["p1", "p2"],
                    "kind": "evidence_backed",
                    "confidence": 0.6,
                }
            ],
        }
    )
    ideas = res.data["ideas"]
    assert ideas and ideas[0]["research_questions"] and ideas[0]["objectives"]
    assert res.data["label"].startswith("PROPOSED")
    assert "mAP" in " ".join(ideas[0]["metrics"]) or ideas[0]["metrics"]


def test_skill_input_validation():
    skill = CitationFormatSkill()
    with pytest.raises(ValueError):
        import asyncio

        asyncio.get_event_loop().run_until_complete(skill.run({"style": "IEEE"}))  # missing entries


def test_gap_titles_are_readable_and_distinct_from_quotes():
    """A gap title must stand alone; it cannot just echo a raw sentence fragment."""
    from app.skills.gap_matrix import GapMatrixSkill

    clause = GapMatrixSkill._clause(
        "These include the lack of standardised State of Health (SOH) estimation "
        "and second-life grading criteria for retired battery packs in Europe."
    )
    assert clause.startswith("The lack")
    assert "These include" not in clause
    assert len(clause.split()) <= 12

    empty = GapMatrixSkill._clause("")
    assert empty == ""
