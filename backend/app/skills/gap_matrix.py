"""GapMatrixSkill — comparison matrix + evidence-linked candidate gaps (Lab 3, Lab 9).

Every gap produced must name the papers that suggest it. Gaps are labelled either
`evidence_backed` (a source explicitly states a limitation) or `hypothesis`
(a pattern across papers that no single paper states).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agents.domain import get_domain
from app.services.text_analysis import LIMITATION_MARKERS, analyse_abstract, extract_method_signals
from app.skills.base import Skill, SkillResult
from app.skills.literature_summarizer import PaperIn


class GapMatrixInput(BaseModel):
    topic: str
    papers: list[PaperIn]
    domain: str = "computer_science"
    max_gaps: int = 6


class MatrixRow(BaseModel):
    paper_id: str
    title: str
    year: int | None = None
    venue: str | None = None
    method_signals: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    has_abstract: bool = False


class GapItem(BaseModel):
    title: str
    description: str
    rationale: str
    evidence_paper_ids: list[str]
    evidence_quotes: list[dict[str, Any]] = Field(default_factory=list)
    kind: str = "hypothesis"  # evidence_backed | hypothesis
    confidence: float = 0.0
    feasibility: str = ""
    suggested_metrics: list[str] = Field(default_factory=list)


class GapMatrixOutput(BaseModel):
    matrix: list[MatrixRow]
    gaps: list[GapItem]
    coverage: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


SYSTEM = (
    "You are a research gap analyst. You receive retrieved papers with their real abstracts. "
    "Propose candidate research gaps that are supported by those papers. "
    "Rules: (1) every gap MUST reference at least one paper index from the input; "
    "(2) if a gap comes from a limitation a paper explicitly states, set kind='evidence_backed' "
    "and quote the sentence; (3) otherwise set kind='hypothesis' and explain the cross-paper pattern; "
    "(4) never invent papers, venues, datasets or results; "
    "(5) confidence must reflect evidence strength, not enthusiasm."
)


class GapMatrixSkill(Skill):
    name = "GapMatrixSkill"
    description = "Build a method/dataset/limitation comparison matrix and candidate gaps."
    instructions = SYSTEM
    input_schema = GapMatrixInput
    output_schema = GapMatrixOutput
    llm_schema = None  # custom LLM path: schema depends on supplied paper ids
    fallback_on_llm_failure = True

    # ------------------------------------------------------------------ matrix
    def build_matrix(self, papers: list[dict[str, Any]]) -> list[MatrixRow]:
        rows = []
        for p in papers:
            text = f"{p['title']} {p.get('abstract') or ''}"
            analysis = analyse_abstract(p["title"], p.get("abstract"))
            rows.append(
                MatrixRow(
                    paper_id=p["id"],
                    title=p["title"],
                    year=p.get("year"),
                    venue=p.get("venue"),
                    method_signals=extract_method_signals(text),
                    datasets=analysis["datasets"],
                    limitations=analysis["limitations"],
                    has_abstract=bool(p.get("abstract")),
                )
            )
        return rows

    def _coverage(self, matrix: list[MatrixRow]) -> dict[str, Any]:
        n = len(matrix) or 1
        methods: dict[str, int] = {}
        datasets: dict[str, int] = {}
        for row in matrix:
            for m in row.method_signals:
                methods[m] = methods.get(m, 0) + 1
            for d in row.datasets:
                datasets[d] = datasets.get(d, 0) + 1
        years = [r.year for r in matrix if r.year]
        return {
            "papers": len(matrix),
            "with_abstract": sum(1 for r in matrix if r.has_abstract),
            "abstract_coverage": round(sum(1 for r in matrix if r.has_abstract) / n, 3),
            "with_stated_limitations": sum(1 for r in matrix if r.limitations),
            "limitation_coverage": round(sum(1 for r in matrix if r.limitations) / n, 3),
            "method_frequency": dict(sorted(methods.items(), key=lambda kv: -kv[1])),
            "dataset_frequency": dict(sorted(datasets.items(), key=lambda kv: -kv[1])),
            "year_range": [min(years), max(years)] if years else None,
        }

    # --------------------------------------------------------------- LLM path
    def build_messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        papers = payload["papers"][:20]
        domain = get_domain(payload.get("domain"))
        blocks = []
        for i, p in enumerate(papers):
            blocks.append(
                f"[{i}] {p['title']} ({p.get('year')})\n"
                f"    abstract: {(p.get('abstract') or '(none)')[:1200]}"
            )
        user = (
            f"Topic: {payload['topic']}\nDomain: {domain.label}\n\n"
            + "\n".join(blocks)
            + "\n\nReturn JSON: {\"gaps\":[{\"title\":\"\",\"description\":\"\",\"rationale\":\"\","
            "\"evidence_indexes\":[0,3],\"evidence_quotes\":[{\"index\":0,\"quote\":\"\"}],"
            "\"kind\":\"evidence_backed|hypothesis\",\"confidence\":0.0,\"feasibility\":\"\","
            "\"suggested_metrics\":[]}]} with at most "
            f"{payload.get('max_gaps', 6)} gaps."
        )
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    async def run(self, payload: dict[str, Any]) -> SkillResult:
        data = self.validate_input(payload)
        papers = data["papers"]
        matrix = self.build_matrix(papers)
        coverage = self._coverage(matrix)
        by_index = {i: p for i, p in enumerate(papers)}

        llm_gaps, generated_by, warnings, error = await self._llm_gaps(data, by_index)
        if llm_gaps is None:
            gaps, fb_warnings = self.heuristic_gaps(data, matrix, papers)
            warnings.extend(fb_warnings)
            generated_by = "heuristic-extraction"
        else:
            gaps = llm_gaps

        out = GapMatrixOutput(
            matrix=matrix,
            gaps=gaps[: data.get("max_gaps", 6)],
            coverage=coverage,
            note=(
                "Matrix cells are extracted from retrieved abstracts. "
                f"Gaps: {generated_by}. Evidence ids point at real stored papers."
            ),
        )
        return SkillResult(
            ok=True,
            data=out.model_dump(),
            generated_by=generated_by,
            warnings=warnings,
            error=error,
            llm_used=generated_by.startswith("ollama:"),
        )

    async def _llm_gaps(
        self, data: dict[str, Any], by_index: dict[int, Any]
    ) -> tuple[list[GapItem] | None, str, list[str], str | None]:
        from pydantic import BaseModel

        from app.services.llm import get_llm

        class _Quote(BaseModel):
            index: int
            quote: str = ""

        class _Gap(BaseModel):
            title: str
            description: str = ""
            rationale: str = ""
            evidence_indexes: list[int] = Field(default_factory=list)
            evidence_quotes: list[_Quote] = Field(default_factory=list)
            kind: str = "hypothesis"
            confidence: float = 0.0
            feasibility: str = ""
            suggested_metrics: list[str] = Field(default_factory=list)

        class _Gaps(BaseModel):
            gaps: list[_Gap]

        llm = get_llm()
        if not (await llm.health()).get("available"):
            return None, "", [], None
        res = await llm.chat_structured(self.build_messages(data), _Gaps, temperature=0.2, num_predict=1600)
        if not res.ok or res.data is None:
            return None, "", [f"gap LLM path unavailable: {res.error}"], res.error

        gaps: list[GapItem] = []
        dropped = 0
        for g in res.data.gaps:
            ids = [by_index[i]["id"] for i in g.evidence_indexes if i in by_index]
            if not ids:
                dropped += 1  # an ungrounded gap is not publishable
                continue
            quotes = [
                {"paper_id": by_index[q.index]["id"], "quote": q.quote[:400]}
                for q in g.evidence_quotes
                if q.index in by_index and q.quote.strip()
            ]
            kind = "evidence_backed" if g.kind == "evidence_backed" or quotes else "hypothesis"
            gaps.append(
                GapItem(
                    title=g.title.strip()[:300],
                    description=g.description.strip(),
                    rationale=g.rationale.strip(),
                    evidence_paper_ids=ids,
                    evidence_quotes=quotes,
                    kind=kind,
                    confidence=max(0.0, min(1.0, float(g.confidence))),
                    feasibility=g.feasibility,
                    suggested_metrics=g.suggested_metrics[:8],
                )
            )
        warnings = [f"model-generated gaps — validate before use ({dropped} ungrounded gap(s) dropped)"]
        return gaps, "ollama", warnings, None

    # ---------------------------------------------------- deterministic path
    @staticmethod
    def _clause(quote: str, max_words: int = 12, limit: int = 120) -> str:
        """A short, distinctive clause from a quoted sentence.

        The gap title must be readable on its own; a raw sentence fragment starting
        with "These include" or "To address these limitations," is not.
        """
        text = " ".join((quote or "").replace("\u201c", "").replace("\u201d", "").split())
        text = text.strip(' "\'()')
        for lead in (
            "These include ", "This includes ", "To address these limitations, ", "To address this, ",
            "However, ", "Based on ", "Key challenges, including ", "The results show that ",
            "Our results show that ", "We find that ", "It is worth noting that ",
        ):
            if text.lower().startswith(lead.lower()):
                text = text[len(lead):]
                text = text[0].upper() + text[1:] if text else text
                break
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]).rstrip(",;:.-")
        if len(text) > limit:
            text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.-")
        return text

    def heuristic_gaps(
        self, data: dict[str, Any], matrix: list[MatrixRow], papers: list[dict[str, Any]]
    ) -> tuple[list[GapItem], list[str]]:
        domain = get_domain(data.get("domain"))
        gaps: list[GapItem] = []
        warnings = ["gaps derived deterministically from abstract text (LLM unavailable)"]

        # 1. Explicitly stated limitations -> evidence_backed gaps
        limit_buckets: dict[str, list[tuple[str, str]]] = {}
        for row in matrix:
            for sent in row.limitations:
                key = "limitation"
                low = sent.lower()
                if "future work" in low:
                    key = "future_work"
                elif "dataset" in low or "data" in low:
                    key = "data_limitation"
                elif "general" in low or "domain" in low or "cross-" in low:
                    key = "generalisation"
                elif "scale" in low or "comput" in low or "resource" in low:
                    key = "compute"
                elif "real-time" in low or "latency" in low or "deploy" in low:
                    key = "deployment"
                limit_buckets.setdefault(key, []).append((row.paper_id, sent))

        titles = {
            "limitation": "Limitations acknowledged by the current literature",
            "future_work": "Directions the authors themselves defer to future work",
            "data_limitation": "Data and dataset constraints reported by the studies",
            "generalisation": "Cross-domain generalisation remains unaddressed",
            "compute": "Compute and resource constraints limit reported methods",
            "deployment": "Deployment and real-time constraints are under-evaluated",
        }
        for key, items in sorted(limit_buckets.items(), key=lambda kv: -len(kv[1])):
            ids = list({pid for pid, _ in items})
            quotes = [{"paper_id": pid, "quote": quote[:400]} for pid, quote in items[:3]]
            lead_quote = items[0][1].strip().rstrip(".")
            gaps.append(
                GapItem(
                    title=(
                        f"{titles.get(key, f'Open issue: {key}')}: "
                        f"{self._clause(lead_quote)}"
                        if self._clause(lead_quote)
                        else titles.get(key, f"Open issue: {key}")
                    ),
                    description=(
                        f"{len(items)} retrieved paper(s) explicitly raise this constraint in their "
                        f"abstracts. The recurring statement suggests a direction the field has not "
                        f"resolved."
                    ),
                    rationale="Direct evidence: the quoted sentences are the authors' own words.",
                    evidence_paper_ids=ids,
                    evidence_quotes=quotes,
                    kind="evidence_backed",
                    confidence=round(min(0.9, 0.35 + 0.15 * len(items)), 2),
                    feasibility="Assessable from the retrieved literature; implementation effort unknown.",
                    suggested_metrics=domain.evaluation_metrics[:3],
                )
            )

        # 2. Cross-paper pattern: methods present but a metric/dataset angle missing
        methods: dict[str, set[str]] = {}
        for row in matrix:
            for m in row.method_signals:
                methods.setdefault(m, set()).add(row.paper_id)
        if methods and len(papers) >= 3:
            top_method, m_ids = max(methods.items(), key=lambda kv: len(kv[1]))
            missing = [p["id"] for p in papers if p["id"] not in m_ids]
            if missing:
                gaps.append(
                    GapItem(
                        title=f"Limited methodological diversity: dominance of '{top_method}' approaches",
                        description=(
                            f"{len(m_ids)} of {len(papers)} retrieved papers show '{top_method}' signals, "
                            f"while {len(missing)} use different or unstated methods. Comparative evidence "
                            f"between these families is thin in the retrieved set."
                        ),
                        rationale=(
                            "Pattern observed across the retrieved set; no single paper states this gap, "
                            "so it is a hypothesis, not a cited fact."
                        ),
                        evidence_paper_ids=sorted(m_ids)[:5],
                        evidence_quotes=[],
                        kind="hypothesis",
                        confidence=round(min(0.7, len(m_ids) / max(len(papers), 1)), 2),
                        feasibility="Requires a controlled comparison study.",
                        suggested_metrics=domain.evaluation_metrics[:3],
                    )
                )

        # 3. Abstract-availability warning is a data-quality note, not a gap
        no_abstract = [p["id"] for p in papers if not p.get("abstract")]
        if no_abstract:
            warnings.append(
                f"{len(no_abstract)} of {len(papers)} papers had no abstract; their gaps could not be "
                "assessed from text. Retrieve full text before relying on them."
            )
        if not gaps:
            warnings.append(
                "No limitations were stated in any retrieved abstract, so no evidence-backed gap "
                "could be derived without a language model. This is reported, not hidden."
            )
        return gaps, warnings
