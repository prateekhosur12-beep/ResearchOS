# 02 — Architecture and Workflow

## 1. System shape

```
┌────────────────────────────────────────────── Browser (React 18 + TS + Vite + Tailwind)
│  9 tabs: Overview · Literature · Gaps & Ideas · Draft · Citations ·
│          Venues·Funding·People · Trace & Audit · Exports · System
│  Only real HTTP calls — no simulated progress bars, no client-side fake data.
└───────────────▲──────────────────────────────────────────────────────────────
                │ JSON + Server-Sent Events (/api/runs/{id}/events)
┌───────────────┴──────────────────────────────────────────────────────────────
│ FastAPI (app/main.py)  ·  serves the API *and* the built SPA from one origin
│  routers: projects · runs · workspace · governance · system
│  error envelope: {error, detail, hint?, request_id}; validation → 422 with field path
└───────────────┬──────────────────────────────────────────────────────────────
                │
      ┌─────────┴──────────┐
      │ WorkflowService    │  background task per run, per project
      │ + AgentRuntime     │  step timing, retries, tracing, audit chain, cancellation
      └─────────┬──────────┘
                │
      ┌─────────▼───────────────────────────────────────────── LangGraph (Lab 7)
      │  discover ──(revise)──► revise_search ──┐
      │     │◄─────────────────────────────────┘
      │     ├─(stop)► no_evidence ► END
      │     └─(gap)─► gap_analysis ► deep_research ► ideas ► drafting
      │                                    ▲                   │
      │                                    │            citation_audit
      │                              draft_revision ◄──(revise_draft)
      │                                                    │(continue)
      │                                               radar ► collaboration ► approval
      │                                                                        │
      │                                                                    finalize ► END
      └─────────┬────────────────────────────────────────────────────────────
                │ every external action goes through the tool runner
      ┌─────────▼──────────────┐        ┌────────────────────────────┐
      │ ToolRunner (14 tools)  │──stdio─►│ MCP server (app/mcp)       │
      │ validation + records   │◄────────│ same 14 tools, protocol    │
      └─────────┬──────────────┘ fallback└────────────────────────────┘
                │
   ┌────────────┼──────────────┬───────────────────┬──────────────────┐
   ▼            ▼              ▼                   ▼                  ▼
 OpenAlex    Crossref       arXiv            Ollama (qwen2.5:3b)   SQLite (17 tables)
 (live)      (live)         (live)           chat + embeddings     projects, papers,
                                            honest fallback        gaps, drafts, traces,
                                                                   audit chain, exports
```

## 2. The graph, exactly as compiled

Nodes (from `build_graph(...).get_graph()`): `discover`, `revise_search`,
`gap_analysis`, `deep_research`, `ideas`, `drafting`, `citation_audit`,
`draft_revision`, `radar`, `collaboration`, `approval`, `finalize`, `no_evidence`.

Edges:

| From | To | Condition |
|---|---|---|
| `__start__` | `discover` | always |
| `discover` | `gap_analysis` | `route_after_discovery` → "gap" (target met, or revision budget spent) |
| `discover` | `revise_search` | "revise" (records < `min_papers` and revisions left) |
| `discover` | `no_evidence` | "stop" (zero records from every source) |
| `revise_search` | `discover` | always (next plan uses different queries) |
| `gap_analysis` | `deep_research` | always |
| `deep_research` | `ideas` | always |
| `ideas` | `drafting` | always |
| `drafting` | `citation_audit` | always |
| `citation_audit` | `draft_revision` | `route_after_citation` → "revise_draft" (unresolved DOI / missing entry, budget left) |
| `citation_audit` | `radar` | "continue" |
| `draft_revision` | `drafting` | always |
| `radar` | `collaboration` | always |
| `collaboration` | `approval` | always |
| `approval` | `finalize` | always (the run pauses in `awaiting_approval`; export stays blocked) |
| `finalize` / `no_evidence` | `__end__` | — |

Both loops are bounded: `MAX_GRAPH_REVISIONS` (default 2) caps discovery revisions *and*
draft revisions, and `recursion_limit=40` is set on `ainvoke`. Nothing in the graph
can loop forever.

## 3. Agent responsibilities

| Agent | Module | What it does (no fabrication) | Deterministic path when Ollama is absent |
|---|---|---|---|
| Literature Discovery | `agents/discovery.py` | plan queries → call 3 sources in parallel → dedupe → rank → save → observe → decide whether to revise (max 3) | the loop itself is deterministic; the *optional* query expansion comes from Ollama, otherwise query variants are rule-based |
| Gap & Idea | `agents/gap.py` | build an evidence matrix from abstracts, derive gaps only where ≥2 papers state a constraint, attach verbatim quotes | yes — `skills/gap_matrix.py` heuristic + `skills/research_question.py` templates; every gap cites `evidence_paper_ids` |
| Deep Research | `agents/deep_research.py` | decompose into sub-questions, run extra searches per sub-question, write an evidence table | yes — synthesis is mechanical; a warning says "no prose synthesis" |
| Drafting | `agents/drafting.py` | assemble a proposal manuscript from retrieved records; bibliography = stored papers only | yes — `skills/manuscript_section.py` templates with `[Pn]` keys |
| Citation & Compliance | `agents/citation.py` | resolve every DOI through Crossref/OpenAlex, check markers ↔ bibliography, flag unused entries | yes — pure metadata verification, no model needed |
| Funding & Journal Radar | `agents/radar.py` | venues (ISSN/publisher), funders from OpenAlex `grants`, collaborators from authorship overlap | yes — data extraction only |
| Collaboration | `agents/collaboration.py` | rank authors by corpus overlap and topic similarity, cite the papers that justify each suggestion | yes |
| Export (gatekeeper) | `agents/export.py` | 9 artefact kinds; 3 are approval-gated | n/a |

## 4. Data flow for one run (measured, `2026-10-30 03:29`, topic *contrastive learning for medical image segmentation*)

```
POST /api/projects/{id}/runs
  → 15 raw records (openalex 5 @670 ms, crossref 5 @284 ms, arxiv 5 @930 ms, all via MCP)
  → dedupe: 15 → 14 unique (1 merged on DOI)
  → 14 papers stored + embedded (lexical-hash-v1 fallback, labelled)
  → 2 gaps, both with evidence ids + verbatim quotes
  → deep research: 4 sub-questions, +8 extra records retrieved
  → 2 research ideas
  → draft v1: 12 references, 11 771 chars, IEEE style
  → citation audit: 12 refs / 12 markers / 11 DOI verified / 1 DOI unavailable / 0 failed
  → radar: venues + funders + 10 collaborators
  → approval request created → run status = awaiting_approval
Trace: 7 agent steps, 26 tool invocations, all transport = mcp
```

## 5. Honesty mechanics (why results cannot be faked silently)

1. **No static corpus.** Every paper row comes from an HTTP response stored with
   `source_queries_json`, `retrieved_at`, and `sources_json`; the UI shows the source
   chips and the original retrieval time.
2. **Per-source truth.** A failed source becomes a `source_attempts` row with
   `status=error|timeout` and a message; the run continues only if another source answered,
   and the failure is listed in `stats_json.failed_sources` and shown in the UI.
3. **LLM absence is a first-class state.** `llm.health()` is probed live; when it is
   down the agents return `generated_by="heuristic"` and warnings such as
   *"LLM unavailable: the report contains mechanical evidence summaries only, no prose synthesis"*.
   Nothing is invented to fill the gap.
4. **Grounded citations only.** The bibliography is built from stored `Paper` rows; the
   draft cannot cite a paper the project does not hold (asserted in
   `test_lab14_capstone_e2e::test_complete_studio_workflow`).
5. **Claim support is not claimed.** The citation report contains
   `claim_level_evidence_check: "not_evaluated"` and a sentence saying verification
   proves the DOI resolves — it does **not** prove the source supports the claim.
6. **Approval gate is server-side.** `manuscript_md`, `manuscript_docx` and
   `full_report_md` return HTTP 403 until an `approvals` row is `approved`; the UI
   explains the rule instead of hiding it.
7. **Hash-chained audit log.** Each record stores `prev_hash`/`hash`; `GET
   /api/projects/{id}/audit` re-verifies the chain and reports `broken_at_seq` if a row
   was edited (proved by `test_lab06_runtime::test_audit_chain_detects_tampering`).

## 6. Transport reality

`ToolRunner.start()` tries a real MCP stdio session (`python -m app.mcp.server`);
the handshake, tool list and calls are protocol messages, not function calls in the
same process. If the subprocess cannot start, the runner falls back to the same
registry in-process and **records which transport was used** per invocation
(`tool_invocations.transport`) and per source attempt (`source_attempts.execution_mode`).
Measured on this machine: `MCP stdio session to 'agentic-research-tools'
(protocol 2025-11-25)`, 14 tools, 26 invocations per run, all `mcp`.
