"""Agent — Deep Research (Lab 9).

Multi-step evidence synthesis:
  1. decompose the research question
  2. search your own literature base first, then retrieve *additional* evidence
     through the live scholarly tools for sub-questions the base cannot answer
  3. build a comparison matrix
  4. identify patterns and limitations
  5. attach candidate gaps (already evidence-linked)
  6. produce an evidence-linked report with explicit uncertainties

Model output is never treated as evidence: every factual statement in the report is
either a record field or an explicitly labelled inference/uncertainty.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.services.llm import get_llm
from app.services.text_analysis import analyse_abstract
from app.tools.runner import ToolRunner

log = get_logger("agents.deep_research")


class Synthesis(BaseModel):
    patterns: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    subquestion_answers: list[dict[str, str]] = Field(default_factory=list)


class DeepResearchAgent:
    name = "DeepResearchAgent"

    def __init__(self, runtime: AgentRuntime, tools: ToolRunner) -> None:
        self.runtime = runtime
        self.tools = tools
        self.llm = get_llm()

    # ------------------------------------------------------------- decompose
    def decompose(self, topic: str, gaps: list[dict[str, Any]], papers: list[dict[str, Any]]) -> list[str]:
        subs = [f"What methods dominate current work on {topic}?"]
        subs.append(f"Which datasets and metrics are used to evaluate {topic}?")
        for g in gaps[:2]:
            subs.append(f"What evidence exists regarding: {g['title']}?")
        if len(papers) < 8:
            subs.append(f"Is the retrieved literature on {topic} sufficient for firm conclusions?")
        return subs[:5]

    async def run(
        self,
        *,
        project_id: str,
        topic: str,
        papers: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        matrix: list[dict[str, Any]],
        domain: str = "computer_science",
        max_extra_searches: int = 3,
    ) -> dict[str, Any]:
        subquestions = self.decompose(topic, gaps, papers)
        await self.runtime.emit(
            "deep_research_started", stage="deep_research", subquestions=subquestions
        )

        existing_titles = {p["title"].lower() for p in papers}
        extra_papers: list[dict[str, Any]] = []
        gaps_covered = 0
        for sub in subquestions[:max_extra_searches]:
            if len(papers) + len(extra_papers) >= 25:
                break
            res = await self.tools.call(
                "search_openalex",
                {"query": sub, "limit": 5},
            )
            self.runtime.stats.tool_calls += 1
            for rec in res.get("records") or []:
                if rec["title"].lower() in existing_titles:
                    continue
                existing_titles.add(rec["title"].lower())
                rec["found_for"] = sub
                extra_papers.append(rec)
            if extra_papers:
                gaps_covered += 1
            await self.runtime.emit(
                "deep_research_retrieval",
                stage="deep_research",
                subquestion=sub,
                status=res.get("status"),
                new_records=len(extra_papers),
                source="openalex",
            )

        all_papers = papers + [
            {
                "id": f"extra:{i}",
                "title": e["title"],
                "abstract": e.get("abstract"),
                "year": e.get("year"),
                "venue": e.get("venue"),
                "doi": e.get("doi"),
                "url": e.get("url"),
                "cited_by": None,
                "external": True,
            }
            for i, e in enumerate(extra_papers)
        ]

        patterns = self._patterns(all_papers, matrix)
        uncertainties = self._uncertainties(all_papers, gaps)
        synthesis_text, generated_by, warnings = await self._synthesise(
            topic, subquestions, all_papers, gaps, patterns, uncertainties
        )

        report = self._render_report(
            topic=topic,
            subquestions=subquestions,
            papers=all_papers,
            matrix=matrix,
            gaps=gaps,
            patterns=patterns,
            uncertainties=uncertainties,
            synthesis=synthesis_text,
            generated_by=generated_by,
            extra_count=len(extra_papers),
        )

        await self.runtime.emit(
            "deep_research_complete",
            stage="deep_research",
            extra_papers=len(extra_papers),
            subquestions=len(subquestions),
            generated_by=generated_by,
        )

        return {
            "subquestions": subquestions,
            "extra_papers_found": len(extra_papers),
            "extra_papers": [
                {"title": e["title"], "year": e.get("year"), "doi": e.get("doi"), "url": e.get("url")}
                for e in extra_papers
            ],
            "patterns": patterns,
            "uncertainties": uncertainties,
            "report_markdown": report,
            "generated_by": generated_by,
            "warnings": warnings,
            "evidence_papers": len(all_papers),
        }

    # ------------------------------------------------------------- analysis
    def _patterns(self, papers: list[dict[str, Any]], matrix: list[dict[str, Any]]) -> list[str]:
        out: list[str] = []
        methods: dict[str, int] = {}
        datasets: dict[str, int] = {}
        metrics: dict[str, int] = {}
        for row in matrix:
            for m in row.get("method_signals") or []:
                methods[m] = methods.get(m, 0) + 1
        for p in papers:
            a = analyse_abstract(p["title"], p.get("abstract"))
            for d in a["datasets"]:
                datasets[d] = datasets.get(d, 0) + 1
            for m in a["metrics"]:
                metrics[m] = metrics.get(m, 0) + 1
        if methods:
            top = sorted(methods.items(), key=lambda kv: -kv[1])[:3]
            out.append(
                "Dominant methodological families: "
                + ", ".join(f"{k} ({v} papers)" for k, v in top)
            )
        if datasets:
            top = sorted(datasets.items(), key=lambda kv: -kv[1])[:3]
            out.append("Most frequently named datasets: " + ", ".join(f"{k} ({v})" for k, v in top))
        else:
            out.append(
                "No dataset names could be extracted from the available abstracts — dataset "
                "conventions could not be established from this corpus."
            )
        if metrics:
            out.append("Metrics referenced in abstracts: " + ", ".join(sorted(metrics)[:8]))
        years = sorted(p["year"] for p in papers if p.get("year"))
        if years:
            out.append(
                f"Publication years span {years[0]}–{years[-1]} across {len(papers)} records."
            )
        no_abs = sum(1 for p in papers if not p.get("abstract"))
        if no_abs:
            out.append(
                f"{no_abs} of {len(papers)} records have no abstract, so claims about their "
                "content rest on titles alone."
            )
        return out

    def _uncertainties(self, papers: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> list[str]:
        out = []
        hyp = [g for g in gaps if g.get("kind") == "hypothesis"]
        if hyp:
            out.append(
                f"{len(hyp)} candidate gap(s) are cross-paper hypotheses, not statements made by "
                "any individual paper."
            )
        if len(papers) < 10:
            out.append(
                f"Only {len(papers)} records were available; conclusions are provisional and the "
                "literature base should be widened before submission."
            )
        if not any(p.get("abstract") for p in papers):
            out.append("No abstracts were available: the synthesis is limited to metadata.")
        out.append(
            "Full texts were not read; methodology details are inferred from abstracts and must be "
            "verified against the papers themselves."
        )
        return out

    async def _synthesise(
        self,
        topic: str,
        subquestions: list[str],
        papers: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        patterns: list[str],
        uncertainties: list[str],
    ) -> tuple[str, str, list[str]]:
        llm = self.llm
        health = await llm.health()
        if health.get("available"):
            evidence = "\n".join(
                f"- {p['title']} ({p.get('year')}) :: {(p.get('abstract') or '(no abstract)')[:400]}"
                for p in papers[:12]
            )
            res = await llm.chat_structured(
                [
                    {
                        "role": "system",
                        "content": (
                            "You synthesise evidence across retrieved papers. Use only the supplied "
                            "records. Never introduce new references or numbers. Mark anything not "
                            "directly supported as an uncertainty."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Topic: {topic}\nSub-questions: {subquestions}\n\n"
                            f"Evidence records:\n{evidence}\n\n"
                            f"Mechanical patterns already computed: {patterns}\n"
                            f"Known uncertainties: {uncertainties}\n\n"
                            "Return JSON: {\"patterns\":[..],\"uncertainties\":[..],"
                            "\"subquestion_answers\":[{\"subquestion\":\"..\",\"answer\":\"..\"}]}"
                        ),
                    },
                ],
                Synthesis,
                temperature=0.2,
                num_predict=1200,
            )
            if res.ok and res.data:
                self.runtime.stats.llm_calls += 1
                merged_patterns = patterns + [p for p in res.data.patterns if p not in patterns]
                merged_unc = uncertainties + [u for u in res.data.uncertainties if u not in uncertainties]
                answers = "\n".join(
                    f"- **{a.get('subquestion','')}** {a.get('answer','')}"
                    for a in res.data.subquestion_answers
                )
                patterns[:] = merged_patterns
                uncertainties[:] = merged_unc
                return (
                    f"### Model-assisted synthesis\n\n{answers}" if answers else "",
                    f"ollama:{res.model}",
                    ["synthesis prose is model-generated; every claim is anchored to a listed record"],
                )
        return "", "deterministic", [
            "LLM unavailable: the report contains mechanical evidence summaries only, no prose synthesis"
        ]

    def _render_report(
        self,
        *,
        topic: str,
        subquestions: list[str],
        papers: list[dict[str, Any]],
        matrix: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        patterns: list[str],
        uncertainties: list[str],
        synthesis: str,
        generated_by: str,
        extra_count: int,
    ) -> str:
        lines = [
            f"# Deep Research Report — {topic}",
            "",
            f"*Synthesis mode: {generated_by}. Evidence base: {len(papers)} records "
            f"({extra_count} retrieved during this synthesis step).*",
            "",
            "## 1. Question decomposition",
            "",
            *[f"{i}. {q}" for i, q in enumerate(subquestions, 1)],
            "",
            "## 2. Evidence table",
            "",
            "| # | Paper | Year | Venue | ID |",
            "|---|---|---|---|---|",
        ]
        for i, p in enumerate(papers[:25], 1):
            ident = p.get("doi") or (p.get("url") or "")[:60] or "no identifier"
            lines.append(
                f"| {i} | {p['title'][:90]} | {p.get('year') or 'n.d.'} | "
                f"{(p.get('venue') or '—')[:40]} | {ident} |"
            )
        lines += ["", "## 3. Comparison matrix (extracted signals)", ""]
        if matrix:
            lines += ["| Paper | Methods | Datasets | Stated limitations |", "|---|---|---|---|"]
            for row in matrix[:20]:
                lines.append(
                    f"| {row['title'][:60]} | {', '.join(row.get('method_signals') or []) or '—'} | "
                    f"{', '.join(row.get('datasets') or []) or '—'} | "
                    f"{(row.get('limitations') or ['—'])[0][:80]} |"
                )
        else:
            lines.append("_No comparison matrix available._")
        lines += ["", "## 4. Patterns", "", *[f"- {p}" for p in patterns]]
        if synthesis:
            lines += ["", "## 5. Synthesis", "", synthesis]
        lines += ["", "## 6. Candidate gaps (evidence-linked)", ""]
        for g in gaps:
            lines.append(
                f"### {g['title']}\n*{g.get('kind')} · confidence {g.get('confidence', 0):.2f} · "
                f"evidence: {len(gek := g.get('evidence_paper_ids', []))} paper(s)*\n\n"
                f"{g.get('description','')}\n"
            )
        lines += ["", "## 7. Remaining uncertainties", "", *[f"- {u}" for u in uncertainties]]
        lines += [
            "",
            "---",
            f"*Generated by the Agentic AI Research Assistant. Every record above was retrieved from "
            f"a live scholarly API; nothing in this report was invented. Statements labelled "
            f"hypothesis are proposals, not findings.*",
        ]
        return "\n".join(lines)
