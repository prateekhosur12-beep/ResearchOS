"""ManuscriptSectionSkill — write one section of a grounded draft (Lab 3).

The hard constraint: cite only from the supplied bibliography keys, and never state
an experimental result. Numbers may appear only when quoted from a source's own
abstract, and the model is told exactly that.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.domain import get_domain
from app.services.text_analysis import analyse_abstract
from app.skills.base import Skill, SkillResult

SECTION_NAMES = [
    "abstract",
    "introduction",
    "related_work",
    "problem_statement",
    "objectives",
    "methodology",
    "proposed_experiments",
    "limitations",
    "conclusion",
]

SectionName = Literal[
    "abstract",
    "introduction",
    "related_work",
    "problem_statement",
    "objectives",
    "methodology",
    "proposed_experiments",
    "limitations",
    "conclusion",
]


class SourceIn(BaseModel):
    paper_id: str
    key: str = ""  # citation key such as "P3"
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None


class SectionInput(BaseModel):
    section: SectionName
    topic: str
    sources: list[SourceIn] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    idea: dict[str, Any] | None = None
    domain: str = "computer_science"
    word_target: int = 300
    feedback: str | None = None


class SectionOutput(BaseModel):
    section: str
    markdown: str
    citations: list[str] = Field(default_factory=list)
    word_count: int = 0
    basis: str = ""


SYSTEM = (
    "You are drafting one section of an academic manuscript for a student research project. "
    "Absolute rules:\n"
    "1. Cite ONLY with the bracket keys given in the bibliography, e.g. [P1] or [P1][P4].\n"
    "2. NEVER invent a reference, author, venue, DOI or publication year.\n"
    "3. NEVER report experimental results, accuracies or numbers of your own. The project has "
    "run no experiments. Numbers may only be restated if quoted from a supplied abstract, and "
    "then say 'reported by [Pn]'.\n"
    "4. If the supplied sources do not support a claim, write that evidence is missing.\n"
    "5. Write clean Markdown prose (no bullet lists unless the section is objectives or "
    "experiments), in a neutral academic register."
)


class ManuscriptSectionSkill(Skill):
    name = "ManuscriptSectionSkill"
    description = "Draft one manuscript section grounded in the supplied bibliography."
    instructions = SYSTEM
    input_schema = SectionInput
    output_schema = SectionOutput
    bonus = True
    temperature = 0.35

    def _schema(self) -> type[BaseModel]:
        class _Section(BaseModel):
            markdown: str
            citations: list[str] = Field(default_factory=list)

        return _Section

    def _bibliography(self, sources: list[dict[str, Any]]) -> str:
        lines = []
        for s in sources:
            key = s.get("key") or s["paper_id"][:6]
            lines.append(
                f"[{key}] {s['title']} ({s.get('year') or 'n.d.'}) — {s.get('venue') or 'venue unknown'}"
                f" — doi:{s.get('doi') or 'none'}"
            )
        return "\n".join(lines) if lines else "(no sources available)"

    def build_messages(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        domain = get_domain(payload.get("domain"))
        gaps = payload.get("gaps") or []
        gap_txt = "\n".join(f"- {g.get('title')} ({g.get('kind')}): {g.get('description','')[:220]}" for g in gaps) or "- none"
        abstracts = []
        for s in payload["sources"][:10]:
            if s.get("abstract"):
                abstracts.append(f"[{s.get('key')}] {s['title']}: {s['abstract'][:700]}")
        idea = payload.get("idea") or {}
        user = (
            f"Topic: {payload['topic']}\n"
            f"Section to write: {payload['section']}\n"
            f"Target length: ~{payload.get('word_target', 300)} words\n"
            f"Domain: {domain.label}\n"
            f"Domain manuscript rules: {'; '.join(domain.manuscript_rules)}\n\n"
            f"BIBLIOGRAPHY (the only citable works):\n{self._bibliography(payload['sources'])}\n\n"
            f"Candidate gaps identified from this literature:\n{gap_txt}\n\n"
            f"Proposed research idea (if relevant):\n{idea.get('title','(none)')} — "
            f"{idea.get('proposed_methodology','')[:400]}\n\n"
            f"ABSTRACT EXCERPTS available (paraphrase only, do not fabricate beyond these):\n"
            + ("\n".join(abstracts) if abstracts else "(no abstracts available)")
            + (f"\n\nREVISION FEEDBACK from the citation audit:\n{payload['feedback']}" if payload.get("feedback") else "")
            + "\n\nReturn JSON: {\"markdown\": \"...\", \"citations\": [\"P1\",\"P4\"]}"
        )
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    # -------------------------------------------------------------- fallbacks
    async def grounded_fallback(self, payload: dict[str, Any], note: str) -> SkillResult:
        section = payload["section"]
        md = self._template(payload)
        keys = [s.get("key") for s in payload["sources"][:3] if s.get("key")]
        used = sorted({k for k in keys if k and f"[{k}]" in md})
        return SkillResult(
            ok=True,
            data=SectionOutput(
                section=section,
                markdown=md,
                citations=used,
                word_count=len(md.split()),
                basis=note,
            ).model_dump(),
            generated_by="template-from-evidence",
            warnings=[note],
        )

    def _template(self, payload: dict[str, Any]) -> str:
        section = payload["section"]
        topic = payload["topic"]
        domain = get_domain(payload.get("domain"))
        srcs = payload["sources"]
        keys = [s.get("key") or s["paper_id"][:6] for s in srcs]
        c = lambda i: f"[{keys[i]}]" if i < len(keys) else ""  # noqa: E731
        cits = " ".join(c(i) for i in range(min(3, len(keys))))
        gaps = payload.get("gaps") or []
        idea = payload.get("idea") or {}
        top_gap = gaps[0]["title"] if gaps else "an evidence gap in the current literature"

        if section == "abstract":
            return (
                f"**Background.** Research on {topic} has expanded rapidly, with the retrieved "
                f"literature covering {len(srcs)} works {cits}.\n\n"
                f"**Gap.** {top_gap}.\n\n"
                f"**Objective.** This proposal sets out to investigate {topic} through the lens of "
                f"that gap, using {domain.evaluation_metrics[0] if domain.evaluation_metrics else 'domain-standard metrics'} "
                f"and a reproducible baseline protocol.\n\n"
                f"**Method (planned).** {idea.get('proposed_methodology', 'A literature-grounded controlled experiment with ablations.')[:300]}\n\n"
                f"**Status.** This is a *proposal draft*. No experiments have been conducted and no "
                f"empirical results are claimed."
            )
        if section == "introduction":
            return (
                f"Research on {topic} sits at the intersection of several active lines of work. "
                f"Recent studies have established strong baselines {cits}, yet the retrieved corpus "
                f"also shows recurring constraints. A systematic reading of {len(srcs)} records "
                f"points to a specific gap: *{top_gap}*.\n\n"
                f"This matters because progress in {topic} is currently reported under heterogeneous "
                f"protocols, which makes cross-study comparison unreliable. The present work therefore "
                f"takes the identified gap as its starting point rather than proposing yet another "
                f"point solution.\n\n"
                f"The contribution of this proposal is threefold: (i) an evidence-grounded synthesis "
                f"of the retrieved literature, (ii) a formal statement of the gap with explicit "
                f"supporting sources, and (iii) a reproducible experimental plan with named metrics, "
                f"datasets and baselines."
            )
        if section == "related_work":
            groups: dict[str, list[int]] = {}
            for i, s in enumerate(srcs[:12]):
                signals = analyse_abstract(s["title"], s.get("abstract"))["method_signals"] or ["method not stated"]
                for sig in signals[:2]:
                    groups.setdefault(sig, []).append(i)
            paras = []
            labels = {
                "method not stated": "Work with no explicit method named in the abstract",
                "transformer": "Transformer-based work",
                "cnn": "CNN-based work",
                "gnn": "Graph neural network work",
                "statistical": "Statistically-driven work",
                "transfer": "Transfer/deep-transfer learning work",
                "rl": "Reinforcement-learning work",
                "llm": "LLM-based work",
                "federated": "Federated / decentralised work",
            }
            for sig, idxs in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:4]:
                refs = " ".join(c(i) for i in idxs[:4])
                first = srcs[idxs[0]]
                label = labels.get(sig, f"{sig.capitalize()}-based work")
                paras.append(
                    f"**{label}.** {len(idxs)} retrieved work(s) show signals of this family "
                    f"{refs}. For example, *{first['title']}* "
                    f"({first.get('year') or 'n.d.'}) addresses the problem from this angle."
                )
            if not paras:
                paras.append(
                    "No reliable methodological grouping could be derived from the retrieved "
                    "abstracts; related work must be extended before this section is finalised."
                )
            return "\n\n".join(paras) + (
                "\n\nThe groupings above are derived mechanically from abstract vocabulary and "
                "are a starting point for the author's own reading, not a substitute for it."
            )
        if section == "problem_statement":
            key_by_paper = {s["paper_id"]: (s.get("key") or s["paper_id"][:6]) for s in srcs}
            body = []
            for i, g in enumerate(gaps[:3]):
                refs = " ".join(
                    f"[{key_by_paper[pid]}]"
                    for pid in g.get("evidence_paper_ids", [])[:3]
                    if pid in key_by_paper
                )
                body.append(
                    f"**G{i + 1}. {g['title']}** — {g.get('description', '')} "
                    f"(supported by {refs or 'no cited record'}; classified as *{g.get('kind', 'hypothesis')}*)."
                )
            return (
                f"Despite progress on {topic}, the retrieved literature exposes unresolved problems. "
                f"The formal problem this proposal addresses is stated below, each item traceable to "
                f"the sources that motivate it.\n\n" + ("\n\n".join(body) if body else
                "No evidence-backed problem could be derived; the literature base must be widened.")
            )
        if section == "objectives":
            rqs = idea.get("research_questions") or [
                f"Which factors most limit progress on {topic}?",
            ]
            objs = idea.get("objectives") or [
                "Reproduce a strong baseline from the literature",
                "Evaluate one targeted intervention",
            ]
            lines = ["**Research questions**", *[f"- RQ{i + 1}: {q}" for i, q in enumerate(rqs[:4])], "", "**Objectives**"]
            lines += [f"- O{i + 1}: {o}" for i, o in enumerate(objs[:5])]
            return "\n".join(lines)
        if section == "methodology":
            return (
                f"The proposed methodology follows a controlled, reproducible protocol suited to "
                f"{domain.label}.\n\n"
                f"**Phase 1 — Evidence consolidation.** The literature matrix assembled in this project "
                f"({len(srcs)} records) is extended until each identified gap has at least two "
                f"independent supporting sources.\n\n"
                f"**Phase 2 — Baseline reproduction.** A strong published baseline is reproduced on a "
                f"public dataset using the published configuration; deviations are documented.\n\n"
                f"**Phase 3 — Intervention.** {idea.get('proposed_methodology', 'A targeted intervention derived from the gap analysis is implemented and compared against the baseline.')[:500]}\n\n"
                f"**Phase 4 — Evaluation.** Metrics: {', '.join(domain.evaluation_metrics[:4])}. "
                f"Each configuration is repeated with at least three random seeds and reported as "
                f"mean ± standard deviation."
            )
        if section == "proposed_experiments":
            datasets = idea.get("suggested_datasets") or domain.representative_datasets[:2]
            metrics = idea.get("metrics") or domain.evaluation_metrics[:4]
            base = domain.baseline_expectations[:3]
            lines = [
                "| Experiment | Purpose | Dataset | Metric |",
                "|---|---|---|---|",
                f"| E1 Baseline reproduction | Establish comparability | {datasets[0] if datasets else 'TBD'} | "
                f"{metrics[0] if metrics else 'primary metric'} |",
                f"| E2 Proposed intervention | Test the core claim | {datasets[0] if datasets else 'TBD'} | "
                f"{', '.join(metrics[:2])} |",
                f"| E3 Ablation | Isolate components | {datasets[-1] if datasets else 'TBD'} | "
                f"{metrics[0] if metrics else 'primary metric'} |",
                f"| E4 Robustness | Cross-dataset behaviour | "
                f"{datasets[1] if len(datasets) > 1 else 'TBD'} | {', '.join(metrics[:2])} |",
                "",
                "**Controls.** " + "; ".join(base),
                "",
                "No results are reported here: the experiments are planned, not executed.",
            ]
            return "\n".join(lines)
        if section == "limitations":
            missing = sum(1 for s in srcs if not s.get("abstract"))
            return (
                "This draft is transparent about its own limits:\n\n"
                f"- The literature base is {len(srcs)} records retrieved from OpenAlex, Crossref and "
                f"arXiv; {missing} of them lack abstracts, so their findings could not be assessed.\n"
                "- Bibliographic records were retrieved at a point in time; coverage of very recent "
                "work is necessarily incomplete.\n"
                "- Full texts were not read for every record; claims about method details depend on "
                "abstracts and must be verified by the author.\n"
                "- No experiments have been run, so no empirical claim in this draft is supported by "
                "the author's own results.\n"
                "- Research-gap statements marked as *hypothesis* are proposals, not established facts."
            )
        if section == "conclusion":
            return (
                f"This proposal set out to situate a research direction in {topic} on an explicit "
                f"evidence base. The retrieved literature ({len(srcs)} records) points to "
                f"{top_gap.lower()}. The planned work addresses it with a reproducible experimental "
                f"protocol, named metrics and documented baselines.\n\n"
                f"Success will be judged by whether the intervention improves "
                f"{domain.evaluation_metrics[0] if domain.evaluation_metrics else 'the primary metric'} "
                f"against a faithfully reproduced baseline, and by whether the resulting artefacts "
                f"(code, seeds, splits) allow independent replication."
            )
        return f"*(no template for section '{section}')*"

    async def run(self, payload: dict[str, Any]) -> SkillResult:
        data = self.validate_input(payload)
        from app.services.llm import get_llm

        llm = get_llm()
        health = await llm.health()
        if not health.get("available"):
            return await self.grounded_fallback(data, f"LLM unavailable — {health.get('detail','')}")
        res = await llm.chat_structured(
            self.build_messages(data), self._schema(), temperature=self.temperature, num_predict=1400
        )
        if not res.ok or res.data is None:
            return await self.grounded_fallback(data, f"LLM drafting failed ({res.error})")
        md = res.data.markdown.strip()
        allowed = {s.get("key") for s in data["sources"] if s.get("key")}
        invented = _unknown_keys(md, allowed)
        warnings = []
        if invented:
            warnings.append(
                f"model cited keys not in the bibliography and they were stripped: {sorted(invented)}"
            )
            for k in invented:
                md = md.replace(f"[{k}]", "")
        return SkillResult(
            ok=True,
            data=SectionOutput(
                section=data["section"],
                markdown=md,
                citations=sorted({k for k in allowed if k and f"[{k}]" in md}),
                word_count=len(md.split()),
                basis=f"generated by ollama:{res.model} from the supplied bibliography",
            ).model_dump(),
            generated_by=f"ollama:{res.model}",
            warnings=warnings + ["model-generated prose — verify every claim against the cited source"],
            llm_used=True,
        )


def _unknown_keys(markdown: str, allowed: set[str | None]) -> set[str]:
    import re

    found = set(re.findall(r"\[(P\d+|[A-Z]{1,4}\d{0,3})\]", markdown))
    allowed_clean = {k for k in allowed if k}
    return {f for f in found if f not in allowed_clean}
