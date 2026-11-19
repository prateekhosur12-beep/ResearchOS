# 03 — Labs 1–14 → Real Files

Every row names the code that implements the lab and the artefact that proves it ran.
The same table is exposed by the running system at `GET /api/labs` (used by the UI's
**System → Labs 1–14** panel), so the mapping cannot drift from the code.

| Lab | Topic | Implementing files | Proof of execution | Verification |
|---|---|---|---|---|
| **1** | Agent vs chatbot — bounded plan/act/observe/revise loop | `app/agents/discovery.py` (plan → 3 sources → observe → decide), `tools/runner.py` | `workflow_runs.stats_json.discovery.{attempts, queries, execution_history}`, SSE events | `tests/test_lab01_discovery_loop.py` (3 tests: 3 distinct queries, early stop, zero-record honesty) |
| **2** | Tool-using agent — 14 schema-validated tools | `app/tools/specs.py` (pydantic `Input` models), `tools/registry.py`, `tools/impl.py`, `tools/runner.py` | `tool_invocations` rows (args, status, latency, transport), `GET /api/system/tools` | `tests/test_lab02_tools.py` (6 tests: schemas, arg validation, failure propagation, determinism, path traversal) |
| **3** | Reusable skills — summarise, gap matrix, sections, citation styles, research questions | `app/skills/base.py`, `literature_summarizer.py`, `gap_matrix.py`, `manuscript_section.py`, `citation_format.py`, `research_question.py` | `drafts.sections_json[*].generated_by`, `research_gaps.generated_by`, `markdown` | `tests/test_lab03_skills.py` (10 tests incl. LLM-schema rejection → heuristic fallback) |
| **4** | Memory & retrieval — project-scoped corpus + semantic search | `app/db/models.py` (projects, papers, paper_vectors), `app/services/embeddings.py`, `POST /api/projects/{id}/retrieval/search`, tool `retrieve_project_memory` | `paper_vectors` rows (`model`, `dim`), retrieval response with scores | `tests/test_lab04_memory.py` (5 tests: isolation, dedupe, vectors rebuild, cross-project leakage blocked) |
| **5** | MCP connector — real protocol, not a function call | `app/mcp/server.py` (stdio MCP server, 14 tools), `app/mcp/client.py` (session, timeout, error mapping) | `GET /api/system/status → mcp {protocol_version: 2025-11-25, tool_count: 14}`; `tool_invocations.transport="mcp"` | `tests/test_lab05_mcp.py` (5 tests: handshake, tool execution over protocol, traversal blocked inside the server, runner records transport, registry == MCP tool set) |
| **6** | Agent runtime — timing, retries, cancellation, tracing, audit chain | `app/runtime/runtime.py` (`AgentRuntime.run_step`, `emit`, `audit`, `verify_audit_chain`) | `trace_events` (7 steps, µs→ms durations), `audit_log` hash chain | `tests/test_lab06_runtime.py` (4 tests: retry-then-succeed, failure recorded, cancel, tamper detection) |
| **7** | Agentic node graph — LangGraph with conditional edges | `app/graph/state.py` (typed `ResearchState`), `app/graph/workflow.py` (13 nodes, 2 bounded loops), `app/services/workflow_service.py` | `GET /api/runs/{id}/events` (SSE stage stream), `stats_json.stage_log` | `tests/test_lab07_graph.py` (5 tests: routing tables, compiled node set, pause at approval, no-evidence → failed) |
| **8** | Parallel agent swarm — async fan-out with partial failure | `app/services/scholarly/aggregator.py` (`search_all`, `compare_modes`), `dedupe.py`, `ranking.py` | per-source `source_attempts` with latency; `stats_json.discovery.wall_ms` | `tests/test_lab08_parallel.py` (5 tests: **measured** sequential-vs-parallel speed-up, partial failure, timeout, dedupe rules, compare_modes) |
| **9** | Deep research — decompose, retrieve more, synthesise with evidence | `app/agents/deep_research.py`, `GET /api/projects/{id}/deep-research` | `stats_json.deep_research.{subquestions, extra_papers, extra_papers_found}` | `tests/test_lab09_deep_research.py` (3 tests: evidence-linked report, thin-evidence honesty, model-assist labelled) |
| **10** | Observability & resilience — retries, backoff, health | `app/services/scholarly/http.py` (retry/backoff/jitter, no retry on 4xx), `app/services/health.py`, `app/logging_conf.py`, `GET /api/system/status` | `source_attempts.{http_status, attempts, error}`, structured JSON logs, `/api/health` | `tests/test_lab10_resilience.py` (5 tests: 429→retry→ok, 404 not retried, bounded budget, timeout, health endpoint) |
| **11** | Agentic SDLC — typed contracts, tests, docs, evolution | `app/api/*` (pydantic request/response models), `app/schemas/models.py`, `tests/`, this `docs/` folder | `GET /openapi.json` (32 paths), 84 tests, lab map | `tests/test_lab11_api.py` (6 tests: CRUD, 422 shape, 404s, explicit empty states, OpenAPI, tool schemas) |
| **12** | Safety & governance — approval gate, audit, safe paths | `app/api/governance.py` (403 gate, approval decisions, audit chain), `app/agents/citation.py`, `app/agents/export.py` (`APPROVAL_REQUIRED`), `runtime.py` (audit) | HTTP 403 before approval / 200 after; `audit_log` 13 records, chain valid | `tests/test_lab12_governance.py` (6 tests: gate, unlock, claim-vs-metadata honesty, chain, download traversal, export kinds) |
| **13** | Discipline-specific agents — CS conventions as data | `app/agents/domain.py` (domain packs: metrics, baselines, reproducibility checklist, formatting rules), `GET /api/system/domains` | draft sections differ per domain; `draft.style` | `tests/test_lab13_domains.py` (5 tests: aliases, CS pack content, API, metrics flow into manuscript, ideas differ) |
| **14** | Capstone studio — the whole product | `frontend/src/App.tsx` + 9 tabs, `app/main.py` (SPA mount), `smoke_e2e.py`, `tests/test_lab14_capstone_e2e.py` | `docs/09_end_to_end_demo.md` transcript (live APIs) | `tests/test_lab14_capstone_e2e.py` (3 tests: full workflow + 6 gated exports, two topics isolated, partial failure) + `python smoke_e2e.py` → 15/15 live checks |

## Lab → UI surface

| Lab | Where the user sees it |
|---|---|
| 1 | Overview → run card (attempts, queries, records raw → unique) |
| 2 | System → Tools (schemas), Trace → tool invocations |
| 3 | Draft → per-section `generated_by`; Gaps → "generated by" |
| 4 | Literature → search within project; Overview → retrieval note |
| 5 | System → MCP discovery card (protocol, tool count) |
| 6 | Trace & Audit → steps with durations |
| 7 | Overview → stage log; live run panel |
| 8 | Overview → per-source rows (status, latency, records) |
| 9 | Gaps & Ideas → deep research report |
| 10 | System → per-source probe + LLM banner |
| 11 | `/docs` (OpenAPI), System → Labs 1–14 map |
| 12 | Draft → approval banner; Exports → gate explanation; Trace → chain badge |
| 13 | Overview → project domain; Draft → domain-specific section text |
| 14 | The entire application |
