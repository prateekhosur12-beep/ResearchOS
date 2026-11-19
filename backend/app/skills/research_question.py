"""ResearchQuestionSkill — turn evidence-linked gaps into a research proposal (Lab 3)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.domain import get_domain
from app.skills.base import Skill, SkillResult


class GapIn(BaseModel):
    title: str
    description: str = ""
    evidence_paper_ids: list[str] = Field(default_factory=list)
    kind: str = "hypothesis"
    confidence: float = 0.0


class RQInput(BaseModel):
    topic: str
    gaps: list[GapIn] = Field(default_factory=list)
    paper_titles: list[str] = Field(default_factory=list)
    domain: str = "computer_science"
    max_ideas: int = 3


class IdeaOut(BaseModel):
    title: str
    research_questions: list[str]
    objectives: list[str]
    proposed_methodology: str
    suggested_datasets: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    feasibility: str = ""
    supporting_gap_titles: list[str] = Field(default_factory=list)


class RQOutput(BaseModel):
    ideas: list[IdeaOut]
    label: str = "PROPOSED — not conducted research"


SYSTEM = (
    "You are a research design assistant. Turn identified gaps into concrete, feasible research "
    "ideation. Everything you write is a PROPOSAL. Never claim results, never invent datasets that "
    "you cannot name from the provided domain guidance, and keep scope realistic for a single "
    "student project."
)


class ResearchQuestionSkill(Skill):
    name = "ResearchQuestionSkill"
    description = "Generate research titles, questions, objectives, method and metrics from gaps."
    instructions = SYSTEM
    input_schema = RQInput
    output_schema = RQOutput
    llm_schema = None
    temperature = 0.4

    def _schema(self) -> type[BaseModel]:
        class _Idea(BaseModel):
            title: str
            research_questions: list[str] = Field(default_factory=list)
            objectives: list[str] = Field(default_factory=list)
            proposed_methodology: str = ""
            suggested_datasets: list[str] = Field(default_factory=list)
            metrics: list[str] = Field(default_factory=list)
            challenges: list[str] = Field(default_factory=list)
            feasibility: str = ""
            supporting_gap_titles: list[str] = Field(default_factory=list)

        class _Ideas(BaseModel):
            ideas: list[_Idea]

        return _Ideas

    def build_messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        domain = get_domain(payload.get("domain"))
        gap_txt = "\n".join(
            f"- {g['title']}: {g['description']} (evidence: {len(g['evidence_paper_ids'])} paper(s), {g['kind']})"
            for g in payload["gaps"]
        ) or "- (no gaps supplied)"
        user = (
            f"Research topic: {payload['topic']}\n"
            f"Domain: {domain.label}\n"
            f"Typical metrics in this domain: {', '.join(domain.evaluation_metrics[:5])}\n"
            f"Reproducibility expectations: {'; '.join(domain.reproducibility_checklist[:3])}\n\n"
            f"Candidate gaps identified from the literature:\n{gap_txt}\n\n"
            f"Produce at most {payload.get('max_ideas', 3)} research ideas as JSON: "
            "{\"ideas\":[{\"title\":\"\",\"research_questions\":[],\"objectives\":[],"
            "\"proposed_methodology\":\"\",\"suggested_datasets\":[],\"metrics\":[],"
            "\"challenges\":[],\"feasibility\":\"\",\"supporting_gap_titles\":[]}]}"
        )
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    async def grounded_fallback(self, payload: dict[str, Any], note: str) -> SkillResult:
        domain = get_domain(payload.get("domain"))
        topic = payload["topic"]
        gaps = payload.get("gaps") or []
        ideas: list[IdeaOut] = []

        for i, gap in enumerate(gaps[: payload.get("max_ideas", 3)]):
            short = gap["title"].rstrip(".")
            ideas.append(
                IdeaOut(
                    title=f"Addressing {short.lower()} in {topic}",
                    research_questions=[
                        f"To what extent does {short.lower()} hold across the state of the art in {topic}?",
                        f"Which design choices most reduce {short.lower()} without sacrificing "
                        f"{domain.evaluation_metrics[0].split(' /')[0].lower()}?",
                    ],
                    objectives=[
                        f"Systematically characterise the gap: {gap['description'][:200]}",
                        "Establish a reproducible baseline on a public dataset for this topic",
                        "Propose and evaluate one targeted intervention against that baseline",
                    ],
                    proposed_methodology=(
                        "Literature-grounded experiment: (1) reproduce a strong baseline from the "
                        "retrieved literature; (2) implement the targeted intervention; (3) run an "
                        "ablation isolating each change; (4) report mean ± std over ≥3 seeds."
                    ),
                    suggested_datasets=domain.representative_datasets[:2],
                    metrics=domain.evaluation_metrics[:3],
                    challenges=[
                        "Baseline reproduction may differ from the published numbers; document deviations.",
                        "Public dataset licensing or access may restrict scope.",
                    ],
                    feasibility=(
                        f"Derived from {len(gap.get('evidence_paper_ids', []))} supporting paper(s); "
                        "scope is a single-student project. Compute needs must be estimated before "
                        "committing (no compute budget has been verified)."
                    ),
                    supporting_gap_titles=[gap["title"]],
                )
            )

        if not ideas:
            ideas.append(
                IdeaOut(
                    title=f"A systematic evidence map of {topic}",
                    research_questions=[
                        f"What methods, datasets and metrics dominate current work on {topic}?",
                        "Which reported limitations recur across studies?",
                    ],
                    objectives=[
                        "Build a reproducible literature matrix",
                        "Cluster stated limitations into themes",
                        "Derive a prioritised agenda for follow-up experiments",
                    ],
                    proposed_methodology="Systematic mapping study with a documented search protocol.",
                    suggested_datasets=["Retrieved literature corpus (this project)"],
                    metrics=["Coverage of retrieved records", "Inter-rater agreement on theme coding"],
                    challenges=["Requires access to full texts, not only abstracts."],
                    feasibility="Low-cost, no GPU required.",
                    supporting_gap_titles=[],
                )
            )

        return SkillResult(
            ok=True,
            data=RQOutput(ideas=ideas).model_dump(),
            generated_by="template-from-evidence",
            warnings=[note],
        )

    async def run(self, payload: dict[str, Any]) -> SkillResult:
        data = self.validate_input(payload)
        if not data["gaps"]:
            return await self.grounded_fallback(data, "no gaps supplied — generic evidence-map idea")
        from app.services.llm import get_llm

        llm = get_llm()
        health = await llm.health()
        if not health.get("available"):
            return await self.grounded_fallback(data, f"LLM unavailable — {health.get('detail','')}")
        res = await llm.chat_structured(
            self.build_messages(data), self._schema(), temperature=self.temperature, num_predict=1500
        )
        if not res.ok or res.data is None:
            return await self.grounded_fallback(data, f"LLM ideation failed ({res.error})")
        ideas = [IdeaOut(**i.model_dump()) for i in res.data.ideas][: data.get("max_ideas", 3)]
        return SkillResult(
            ok=True,
            data=RQOutput(ideas=ideas).model_dump(),
            generated_by=f"ollama:{res.model}",
            warnings=["model-generated research ideas — proposed, not validated"],
            llm_used=True,
        )
