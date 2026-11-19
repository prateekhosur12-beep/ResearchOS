"""Lab 13 — Discipline-specific rules are data, not code paths."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.domain import DOMAINS, get_domain, list_domains
from app.main import app
from app.skills.manuscript_section import ManuscriptSectionSkill
from app.skills.research_question import ResearchQuestionSkill


def test_domain_lookup_and_aliases():
    assert get_domain("computer_science").key == "computer_science"
    assert get_domain("cs").key == "computer_science"
    assert get_domain("AI").key == "computer_science"
    assert get_domain(None).key == "computer_science"
    assert get_domain("marine biology").key in DOMAINS
    generic = get_domain("sociology")
    assert generic.key == "generic"


def test_cs_pack_carries_concrete_expectations():
    cs = get_domain("computer_science")
    assert any("F1" in m for m in cs.evaluation_metrics)
    assert any("ablation" in b.lower() for b in cs.baseline_expectations)
    assert any("seed" in r.lower() for r in cs.reproducibility_checklist)
    assert cs.formatting_standard == "IEEE"
    assert any("no experimental numbers" in r.lower() for r in cs.manuscript_rules)


def test_domain_is_configurable_via_api():
    with TestClient(app) as client:
        body = client.get("/api/system/domains").json()
        keys = {d["key"] for d in body["domains"]}
        assert "computer_science" in keys
        assert body["default"] == "computer_science"
        assert len(list_domains()) == len(body["domains"])


@pytest.mark.asyncio
async def test_domain_metrics_flow_into_manuscript():
    skill = ManuscriptSectionSkill()
    sources = [
        {
            "paper_id": "p1",
            "key": "P1",
            "title": "A paper",
            "abstract": "We propose a model and report accuracy.",
            "year": 2024,
        }
    ]
    cs = await skill.run(
        {
            "section": "proposed_experiments",
            "topic": "topic",
            "sources": sources,
            "domain": "computer_science",
            "gaps": [],
        }
    )
    generic = await skill.run(
        {
            "section": "proposed_experiments",
            "topic": "topic",
            "sources": sources,
            "domain": "generic",
            "gaps": [],
        }
    )
    assert "F1" in cs.data["markdown"] or "mIoU" in cs.data["markdown"]
    assert "Primary outcome measure" in generic.data["markdown"] or "dataset" in generic.data["markdown"].lower()
    assert cs.data["markdown"] != generic.data["markdown"]
    assert "No results are reported here" in cs.data["markdown"]


@pytest.mark.asyncio
async def test_domain_shapes_research_ideas():
    skill = ResearchQuestionSkill()
    payload_gaps = [
        {
            "title": "Evaluation gap",
            "description": "Metrics vary across papers.",
            "evidence_paper_ids": ["p1"],
            "kind": "evidence_backed",
            "confidence": 0.5,
        }
    ]
    cs = await skill.run({"topic": "t", "domain": "computer_science", "gaps": payload_gaps})
    gen = await skill.run({"topic": "t", "domain": "generic", "gaps": payload_gaps})
    assert cs.data["ideas"][0]["metrics"] != gen.data["ideas"][0]["metrics"]
