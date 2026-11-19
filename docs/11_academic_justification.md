# 11 — Academic Justification

This document ties each design decision to the literature and to the course's learning
outcomes (Labs 1–14). It also states, plainly, what the artefact does **not** establish.

## 1. Why an agent and not a chatbot (Lab 1)

A chatbot answers from its parameters; an agent changes the world and observes the result.
The discovery agent implements the canonical loop *plan → act → observe → decide*
(Yao et al., ReAct, 2022; Wooldridge & Jennings, 1995 on agent architecture) with an
explicit stopping rule and a hard budget of 3 attempts. The observable difference is
recorded, not asserted: `execution_history` stores each attempt's query, per-source
outcome, dedupe statistics and wall time, and the graph routes to `revise_search` only when
the observed record count is below `min_papers`.

## 2. Why tools with schemas (Lab 2)

Tool use is the mechanism by which an LLM's output becomes an *action with consequences*
(Schick et al., Toolformer, 2023; Qin et al., 2023 survey). Our registry gives every tool a
pydantic input model, so an invalid call is rejected **before** any network or subprocess
work, and the rejection is recorded. This is the practical form of "constrained action
space", and it makes tool misuse auditable rather than invisible.

## 3. Why skills are separate from agents (Lab 3)

Skills are stateless, testable transformations with declared input/output schemas;
agents own control flow. This separation (modular composition, cf. Schick et al.) is what
makes the LLM dependency *optional*: the same skill returns either `generated_by="ollama:…"`
or `generated_by="heuristic-extraction"` with an explanation, and the caller cannot tell the
difference except by reading the field — which is exactly the point.

## 4. Why project-scoped memory (Lab 4)

Retrieval-augmented generation reduces hallucination only if the retrieved context is
relevant and attributable (Lewis et al., RAG, 2020). Two consequences are implemented:
(a) every record is stored with its provenance (`sources_json`, `source_queries_json`,
`retrieved_at`) so a claim can be traced back to the exact retrieval; (b) retrieval is
scoped per project, so a second topic cannot inherit another topic's context — the failure
mode usually reported as "contamination" in multi-task assistants (Ji et al., survey on
hallucination, 2023). `test_lab04_memory` asserts the boundary rather than trusting it.

## 5. Why MCP rather than plain function calls (Lab 5)

MCP (Model Context Protocol) standardises the boundary between an agent and its tools, so the
same tools can be consumed by any compliant host. The pedagogical point is that the boundary
is a **protocol**, not a Python import: the tools run in a separate process, speak JSON-RPC
over stdio, negotiate a version and expose schemas. Because that hop can fail, the runner
records which transport actually served each call (`mcp` vs `direct`) — an honest
implementation of a distributed interface rather than a facade.

## 6. Why a runtime with traces (Lab 6)

Agent systems fail in ways that are invisible in the final answer: a step silently retried
forever, a tool timeout swallowed, an approval bypassed. The runtime therefore records every
step with status, attempt count and duration, and appends to a **hash-chained** audit log.
Hash chaining (tamper-evident logs, cf. Schneier & Kelsey, 1999) means post-hoc edits are
detectable, which is what "governance" can honestly promise without a trust anchor.

## 7. Why an explicit graph (Lab 7)

Free-form agent loops are hard to reason about and impossible to bound. LangGraph makes the
control flow a first-class object: 13 named nodes, conditional edges, and two loops whose
revision counters are capped by configuration. This corresponds to the "state machine over
autonomy" position argued in recent agent-engineering practice (e.g. Anthropic's *Building
effective agents*, 2024: prefer workflows for well-understood tasks, agents where the path is
open-ended). Our graph is deliberately hybrid: deterministic where the procedure is known
(dedupe, audit, export) and model-dependent only where judgement is needed (query
reformulation, synthesis).

## 8. Why a parallel swarm (Lab 8)

Independent sources should be queried concurrently: latency is dominated by the slowest
response, not the sum (the classic fan-out/fan-in pattern). We *measure* it —
`compare_modes()` reports sequential vs parallel wall time and per-source latency for the same
queries — rather than claiming a speed-up. Equally important is partial failure: a swarm must
degrade to the healthy subset and say which members failed (cf. saga/compensation patterns in
distributed systems). `failed_sources` is a reported field, not a log line.

## 9. Why "deep research" is decomposed (Lab 9)

A single query cannot cover a research field; decomposition into sub-questions and per-question
retrieval mirrors how systematic reviews are actually conducted (Kitchenham, guidelines for
SLRs; PRISMA-style reporting). The output therefore carries a sub-question list, the extra
records each sub-question retrieved, an evidence table and a section on *remaining
uncertainties* — including explicit statements when evidence is thin.

## 10. Why observability is a lab, not an afterthought (Lab 10)

Production agent systems are judged on their failure behaviour. Retry with exponential backoff
and jitter, no retry on 4xx (a 404 will not become a 200), bounded budgets, per-source health
probes and structured JSON logs are the standard resilience toolkit (Nygard, *Release It!*).
The health endpoint exposes dependency truth instead of a constant `{"status":"ok"}`.

## 11. Why the API contracts are typed (Lab 11)

Pydantic models at the boundary, `openapi.json` generated, and tests that assert the shape of
error bodies are the practical form of interface-first development. The lab's "agentic SDLC"
claim is substantiated by artefacts, not by vocabulary: 84 automated tests, a lab→file map
served by the API, and this documentation set.

## 12. Why human approval gates the manuscript (Lab 12)

Autonomy without a stop condition is a liability (cf. the "human-in-the-loop" requirement in
the EU AI Act's high-risk provisions and in research-integrity guidance on AI-assisted
writing). Two design choices follow: (a) the gate is server-side (`403`), so a client cannot
skip it; (b) the gate is *narrow* — data exports stay available, only the artefacts that read
as authored output require a named human decision, which is recorded in `approvals` and in the
audit chain. Equally, the citation audit refuses to collapse "metadata resolves" into
"claim supported", the exact conflation that makes AI citation checkers misleading.

## 13. Why domain packs are data (Lab 13)

Discipline-specific expectations (metrics, baselines, reproducibility checklists, formatting)
are configuration, not branching code: `app/agents/domain.py` holds a CS pack and a generic
pack, and skills read from whichever pack the project declares. This is the difference between
"an agent that knows CS conventions" and "a system whose conventions can be extended to
another field without touching the agent" — the latter is the extensibility claim the lab
asks for.

## 14. Why the capstone emphasises honest status (Lab 14)

The most consequential design decision in this project is what it refuses to do: no invented
records, no silent demo fallback, no upstream failure hidden behind a placeholder, no "lab
complete" badge justified by a UI panel. Each of those refusals costs something (a run without
an LLM produces visibly plainer prose; a failed source shows up in the overview; an
unverified venue stays unverified). The contribution is therefore not "an agent that writes a
paper" but *an agentic system whose output you can audit* — and the audit tables, the warning
strings and the 84 tests are the evidence.

## 15. What this artefact does not establish

* It does **not** show that LLM-written prose is publication-quality; with no model available
  in the verification environment, all recorded output came from the deterministic paths.
* It does **not** measure scientific quality of the generated proposals; no human evaluation
  study was run, and citation counts are metadata, not impact.
* It does **not** prove hallucination is impossible — it makes invention *detectable*
  (provenance, verbatim quotes, bibliography restricted to stored records, claim-support
  explicitly unevaluated).
* It does **not** generalise beyond the three metadata sources; coverage bias toward open
  metadata and CS/physics preprints is a real constraint on any conclusion drawn from it.

## References (selection)

* Yao et al. (2022). *ReAct: Synergizing Reasoning and Acting in Language Models.*
* Lewis et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.*
* Schick et al. (2023). *Toolformer: Language Models Can Teach Themselves to Use Tools.*
* Qin et al. (2023). *Tool Learning with Foundation Models* (survey).
* Ji et al. (2023). *Survey of Hallucination in Natural Language Generation.*
* Nygard (2018). *Release It! Design and Deploy Production-Ready Software* (2nd ed.).
* Schneier & Kelsey (1999). *Secure Audit Logs to Support Computer Forensics.*
* Kitchenham & Charters (2007). *Guidelines for performing Systematic Literature Reviews.*
* Page et al. (2021). *PRISMA 2020 statement.*
* Anthropic (2024). *Building effective agents.*
* Model Context Protocol specification (2025-11-25 revision, as negotiated by the server).
