"""LiteratureSummarizerSkill — per-paper structured analysis (Lab 3)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.domain import DomainProfile, get_domain
from app.services.scholarly.ranking import build_topic_terms, overlap_score
from app.services.text_analysis import analyse_abstract
from app.skills.base import Skill, SkillResult


class PaperIn(BaseModel):
    id: str
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    sources: list[str] = Field(default_factory=list)


class SummarizerInput(BaseModel):
    topic: str
    papers: list[PaperIn]
    domain: str = "computer_science"
    max_papers: int = 12


class LlmPaperAnalysis(BaseModel):
    index: int = Field(description="0-based index into the supplied papers list")
    research_problem: str = ""
    methodology: str = ""
    datasets: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    relevance_to_topic: str = ""


class LlmSummary(BaseModel):
    analyses: list[LlmPaperAnalysis]


class PaperAnalysisOut(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract_available: bool
    research_problem: str | None = None
    methodology: str | None = None
    datasets: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    relevance_to_topic: str = ""
    matched_terms: list[str] = Field(default_factory=list)
    basis: str = ""


class SummarizerOutput(BaseModel):
    analyses: list[PaperAnalysisOut]
    note: str = ""


SYSTEM = (
    "You are a careful research assistant summarising scholarly abstracts for a literature review. "
    "Use ONLY information present in the supplied title/abstract/metadata. "
    "If a field is not stated, return an empty value or empty list — never guess, never invent "
    "datasets, numbers, venues or findings. Do not describe experiments that are not in the text."
)


class LiteratureSummarizerSkill(Skill):
    name = "LiteratureSummarizerSkill"
    description = "Extract problem, method, datasets, findings and limitations per paper."
    instructions = SYSTEM
    input_schema = SummarizerInput
    output_schema = SummarizerOutput
    llm_schema = LlmSummary
    temperature = 0.1
    max_tokens = 1800

    def build_messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        topic = payload["topic"]
        domain: DomainProfile = get_domain(payload.get("domain"))
        papers = payload["papers"][: payload.get("max_papers", 12)]
        blocks = []
        for i, p in enumerate(papers):
            abstract = (p.get("abstract") or "")[:1600] or "(no abstract available)"
            blocks.append(
                f"[{i}] title: {p['title']}\n"
                f"    year: {p.get('year')}  venue: {p.get('venue')}\n"
                f"    abstract: {abstract}"
            )
        user = (
            f"Research topic: {topic}\n"
            f"Domain: {domain.label}\n\n"
            f"Papers:\n" + "\n".join(blocks) + "\n\n"
            "Return JSON: {\"analyses\":[{\"index\":0,\"research_problem\":\"\",\"methodology\":\"\","
            "\"datasets\":[],\"findings\":[],\"limitations\":[],\"relevance_to_topic\":\"\"}]} "
            "with one object per paper index, in order. Keep each field to 1-2 sentences."
        )
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    def _map_llm(self, papers: list[dict[str, Any]], analyses: list[Any]) -> list[PaperAnalysisOut]:
        """Map validated model output onto the stable output schema."""
        out: list[PaperAnalysisOut] = []
        for item in analyses:
            idx = item.index
            if not isinstance(idx, int) or idx < 0 or idx >= len(papers):
                continue
            p = papers[idx]
            ov = overlap_score(build_topic_terms(p.get("topic_hint", "")), p["title"], p.get("abstract"))
            out.append(
                PaperAnalysisOut(
                    paper_id=p["id"],
                    title=p["title"],
                    year=p.get("year"),
                    venue=p.get("venue"),
                    doi=p.get("doi"),
                    url=p.get("url"),
                    abstract_available=bool(p.get("abstract")),
                    research_problem=item.research_problem or None,
                    methodology=item.methodology or None,
                    datasets=item.datasets,
                    findings=item.findings,
                    limitations=item.limitations,
                    relevance_to_topic=item.relevance_to_topic,
                    matched_terms=ov["matched_terms"][:8],
                    basis="model interpretation of the retrieved abstract — verify against the source",
                )
            )
        return out

    async def run(self, payload: dict[str, Any]) -> SkillResult:
        data = self.validate_input(payload)
        papers = data["papers"][: data.get("max_papers", 12)]
        from app.services.llm import get_llm

        llm = get_llm()
        health = await llm.health()
        if not health.get("available"):
            return await self.grounded_fallback(data, f"LLM unavailable — {health.get('detail','')}")

        res = await llm.chat_structured(
            self.build_messages(data),
            LlmSummary,
            temperature=self.temperature,
            num_predict=self.max_tokens,
        )
        if res.ok and res.data:
            analyses = self._map_llm(papers, res.data.analyses)
            if analyses:
                return SkillResult(
                    ok=True,
                    data=SummarizerOutput(
                        analyses=analyses,
                        note="Fields written by the local model from the retrieved abstracts.",
                    ).model_dump(),
                    generated_by=f"ollama:{res.model}",
                    warnings=["model-generated content — verify against the cited sources"],
                    llm_used=True,
                )
        fallback = await self.grounded_fallback(
            data, f"LLM call or validation failed ({res.error}) — using deterministic extraction"
        )
        fallback.error = res.error
        return fallback

    async def grounded_fallback(self, payload: dict[str, Any], note: str) -> SkillResult:
        topic = payload["topic"]
        terms = build_topic_terms(topic)
        out: list[PaperAnalysisOut] = []
        for p in payload["papers"][: payload.get("max_papers", 12)]:
            analysis = analyse_abstract(p["title"], p.get("abstract"))
            ov = overlap_score(terms, p["title"], p.get("abstract"))
            out.append(
                PaperAnalysisOut(
                    paper_id=p["id"],
                    title=p["title"],
                    year=p.get("year"),
                    venue=p.get("venue"),
                    doi=p.get("doi"),
                    url=p.get("url"),
                    abstract_available=bool(p.get("abstract")),
                    research_problem=analysis["problem"],
                    methodology=analysis["methodology"],
                    datasets=analysis["datasets"],
                    findings=analysis["findings"],
                    limitations=analysis["limitations"],
                    relevance_to_topic=(
                        "overlapping terms: " + ", ".join(ov["matched_terms"][:8])
                        if ov["matched_terms"]
                        else "no strong lexical overlap with the stated topic"
                    ),
                    matched_terms=ov["matched_terms"][:8],
                    basis=analysis["basis"],
                )
            )
        return SkillResult(
            ok=True,
            data=SummarizerOutput(
                analyses=out,
                note=f"{note}. Fields are verbatim extractions, not model interpretations.",
            ).model_dump(),
            generated_by="heuristic-extraction",
            warnings=[note],
        )
