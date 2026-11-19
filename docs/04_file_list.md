# 04 — File List

Every file in the deliverable, one line each. Line counts are current (`wc -l`).

## 1. Root

| Path | Lines | Purpose |
|---|---|---|
| `README.md` | — | index, quick start, deliverable map |
| `docs/01…11_*.md` | — | the eleven required deliverables |

## 2. Backend — application (`backend/app/`, 63 modules, 10 653 lines)

### Entry point & configuration

| File | Lines | Purpose |
|---|---|---|
| `main.py` | 161 | FastAPI app, CORS, error envelope (`validation_error` / 404 / 500 with `request_id`), router mounting, `/api/labs` map, SPA static mount |
| `config.py` | 128 | pydantic-settings `Settings` + `public_snapshot()` (redacted config for the UI) |
| `logging_conf.py` | 56 | JSON structured logging with `request_id` / `run_id` context vars |
| `events.py` | 66 | in-process pub/sub used by the SSE endpoint |

### API layer (`app/api/`)

| File | Lines | Purpose |
|---|---|---|
| `projects.py` | 143 | project CRUD + summary |
| `runs.py` | 231 | create/list runs, run detail, cancel, trace, SSE events, tool invocations, latest state |
| `workspace.py` | 597 | papers, gaps, ideas, draft get/patch/regenerate, citations + re-audit, radar, retrieval search, deep research |
| `governance.py` | 253 | approvals, export creation (403 gate), export listing, safe download, audit chain |
| `system.py` | 69 | health, dependency status (LLM/sources/MCP), tool schemas, domain packs |
| `deps.py` | 51 | shared project/run accessors + 404 handling |
| `schemas/models.py` | 174 | request/response pydantic models |

### Agents (`app/agents/`, 2 354 lines)

| File | Lines | Purpose |
|---|---|---|
| `discovery.py` | 423 | Literature Discovery: plan → parallel search → dedupe/rank → save → observe → revise |
| `gap.py` | 164 | Gap & Idea: evidence matrix → evidence-backed vs hypothesis gaps |
| `deep_research.py` | 346 | decomposition, extra retrieval, evidence-linked report |
| `drafting.py` | 301 | manuscript assembly, bibliography, revision handling |
| `citation.py` | 202 | DOI resolution, marker↔bibliography checks, unused entries |
| `radar.py` | 149 | venues (ISSN), funders (OpenAlex grants), collaborators |
| `collaboration.py` | 93 | author overlap ranking with justification |
| `export.py` | 515 | 9 export kinds; `APPROVAL_REQUIRED` gate |
| `domain.py` | 113 | discipline packs (CS/generic) used by skills |
| `common.py` | 48 | shared agent helpers (warnings, JSON coercion) |

### Skills (`app/skills/`, 1 411 lines)

| File | Lines | Purpose |
|---|---|---|
| `base.py` | 131 | `Skill` base: input schema, LLM structured call, validation, grounded fallback |
| `literature_summarizer.py` | 213 | per-paper analysis (problem/method/datasets/findings/limitations) |
| `gap_matrix.py` | 331 | coverage matrix + evidence-linked gaps, ungrounded gaps dropped |
| `manuscript_section.py` | 367 | 10 section templates (abstract → conclusion), domain-aware |
| `citation_format.py` | 178 | IEEE / APA / BibTeX rendering |
| `research_question.py` | 191 | RQ/objective/idea proposal from gaps |

### Tools & MCP

| File | Lines | Purpose |
|---|---|---|
| `tools/specs.py` | 138 | 14 tool specs with pydantic input models (the contract) |
| `tools/impl.py` | 750 | tool implementations (3 source searches, save, memory, save/read file, compare, venues, funders, collaborators, datasets, stats, audit helpers) |
| `tools/registry.py` | 158 | register/validate/describe/call |
| `tools/runner.py` | 158 | MCP-vs-direct transport, validation-first, per-call records |
| `mcp/server.py` | 198 | stdio MCP server exposing the same 14 tools |
| `mcp/client.py` | 202 | client session, timeout, tool-error mapping, `probe_server()` |

### Retrieval (`app/services/scholarly/`, 1 246 lines)

| File | Lines | Purpose |
|---|---|---|
| `http.py` | 190 | retry/backoff on 429/5xx, no retry on 4xx, `FetchResult` with attempts+latency |
| `openalex.py` | 171 | works + single-work lookup, inverted-index abstract decode |
| `crossref.py` | 141 | works + DOI resolution + venue/ISSN |
| `arxiv.py` | 118 | Atom parsing incl. namespaces, DOI, PDF link |
| `aggregator.py` | 244 | `search_all` (parallel/sequential), per-source reports, `compare_modes` |
| `dedupe.py` | 114 | DOI → arXiv → normalised-title merge, richest-metadata wins |
| `ranking.py` | 145 | relevance/recency/citation score with an explainability blob |
| `records.py` | 122 | `ScholarlyRecord` normal form |

### Services, runtime, graph, DB

| File | Lines | Purpose |
|---|---|---|
| `services/llm.py` | 346 | Ollama client: health (model-installed check), chat, JSON-mode structured call with one repair, embeddings with honest `None` |
| `services/embeddings.py` | 175 | `index_papers`, `semantic_search`, `local_embed` (deterministic lexical hash fallback) |
| `services/health.py` | 45 | live per-source probes |
| `services/text_analysis.py` | 139 | method/dataset/limitation extraction shared by skills and tools |
| `services/workflow_service.py` | 224 | run creation, background execution, status/stats assembly, cancellation |
| `runtime/runtime.py` | 258 | `AgentRuntime`: step timing, retry, emit (SSE+trace), `audit()`, `verify_audit_chain()` |
| `graph/state.py` | 47 | typed `ResearchState` |
| `graph/workflow.py` | 456 | 13 nodes, conditional edges, `WorkflowContext` |
| `db/models.py` | 356 | 17 tables |
| `db/base.py` | 46 | async engine/session, `init_db()` |

### Scripts, config, tests

| File | Lines | Purpose |
|---|---|---|
| `backend/smoke_e2e.py` | 194 | live end-to-end proof (15 checks) |
| `backend/smoke_tools.py` | 41 | tool registry / MCP smoke check |
| `backend/requirements.txt` | 30 | pinned dependencies (verified versions) |
| `backend/.env.example` | 60 | every setting with comments |
| `backend/pytest.ini` | 12 | `asyncio_mode = auto`, markers `live`/`slow`, `testpaths` |
| `backend/tests/conftest.py` | 322 | temp DB, fake scholar (HTTP-level, real payload shapes), fake Ollama, live gating |
| `backend/tests/test_lab01…test_lab14_*.py` | 1 744 | 79 offline tests |
| `backend/tests/test_live_services.py` | 111 | 4 live tests (gated by `RUN_LIVE_TESTS=1`) |
| `backend/tests/test_llm_service.py` | 96 | 8 Ollama client tests |

## 3. Frontend (`frontend/`, 2 784 lines of source + config)

| File | Lines | Purpose |
|---|---|---|
| `src/App.tsx` | 304 | layout, project switcher/create/delete, header with per-source dots, 9 tabs |
| `src/api.ts` | 120 | typed API client, error normalisation |
| `src/types.ts` | 231 | shared response types |
| `src/hooks.ts` | 42 | `useAsync`, `useEventStream` (SSE), polling helper |
| `src/markdown.tsx` | 148 | minimal Markdown renderer (no raw HTML injection) |
| `src/components/RunPanel.tsx` | 295 | start run with real config, live SSE log |
| `src/components/LiteratureTab.tsx` | 222 | paper table, source chips, retrieval times, in-project search |
| `src/components/DraftTab.tsx` | 222 | section view, regenerate, approve/reject, bibliography |
| `src/components/TraceTab.tsx` | 194 | steps, tool invocations (transport), source attempts, audit chain |
| `src/components/ui.tsx` | 166 | Card, Badge, Table, Spinner, ErrorBox primitives |
| `src/components/GapsTab.tsx` | 146 | gaps with quoted evidence, ideas, deep-research report |
| `src/components/RadarTab.tsx` | 134 | venues with verification badge, funders, collaborators |
| `src/components/SystemTab.tsx` | 128 | LLM/source/MCP probing, redacted config, Labs 1–14 map |
| `src/components/OverviewTab.tsx` | 126 | stat tiles, approval banner, run card, stage log |
| `src/components/CitationsTab.tsx` | 112 | audit summary, per-entry verification, re-audit button |
| `src/components/ExportsTab.tsx` | 92 | 9 kinds, gate explanation, previous exports |
| `src/main.tsx` | 10 | React root |
| `vite.config.ts` | 30 | dev proxy `/api` → :8000, build → `../backend/static/ui` |
| `tailwind.config.js`, `postcss.config.js`, `index.html`, `package.json`, `tsconfig.json` | 62 | build configuration |

## 4. Generated at runtime (not source)

| Path | Contents |
|---|---|
| `backend/data/research.db` | SQLite database (17 tables) |
| `backend/exports/{project_id}/` | generated files, one folder per project |
| `backend/static/ui/{index.html,assets/*.js,*.css}` | SPA build output served at `/` |
| `backend/smoke_e2e.db` | isolated DB used by `smoke_e2e.py` (so smoke runs never touch your data) |
