# 01 — Repository Audit

Scope: the state of this repository **as it is now**, after the build. The workspace
contained no pre-existing code for this project (no `agents/`, `tools/`, `graph/`,
`tests/`), so this audit records the baseline that was created, what was removed,
and what is knowingly incomplete — rather than an audit of someone else's code.

Audit date: 2026-10-30.

---

## 1. What exists

```
/home/user
├── backend/                 FastAPI application, agents, tools, MCP server, tests
│   ├── app/                 63 modules, 10 653 lines of Python
│   ├── tests/               17 test modules, 84 tests (2 300+ lines)
│   ├── static/ui/           built React SPA served by FastAPI (index.html + assets/)
│   ├── smoke_e2e.py         end-to-end proof script against live APIs
│   ├── smoke_tools.py       tool/MCP registry smoke check
│   ├── requirements.txt     pinned dependencies (verified versions)
│   ├── pytest.ini           asyncio mode, markers, testpaths
│   └── data/, exports/      runtime artefacts (SQLite DB, generated export files)
├── frontend/                React 18 + TypeScript + Vite + Tailwind SPA
│   └── src/                 18 files, 2 749 lines (9 tabs + shared UI)
└── docs/                    these deliverables (01–11) + README
```

Verified counts (`find … | wc -l`, `wc -l`): **69 backend Python modules**, **16 test
modules**, **18 frontend TS/TSX files**.

## 2. Layers actually implemented

| Layer | Files | Responsibility |
|---|---|---|
| API | `app/api/{projects,runs,workspace,governance,system}.py`, `app/main.py` | 32 paths / 37 operations, static SPA mount, error envelope, `/api/labs` |
| Orchestration | `app/graph/{state,workflow}.py`, `app/services/workflow_service.py` | LangGraph graph, conditional edges, background execution, run status |
| Agents (7) | `app/agents/{discovery,gap,drafting,citation,radar,collaboration,deep_research}.py` + `export.py`, `domain.py`, `common.py` | the seven named agents |
| Skills (5) | `app/skills/{literature_summarizer,gap_matrix,manuscript_section,citation_format,research_question}.py`, `base.py` | reusable, schema-validated LLM/heuristic skills |
| Tools (14) | `app/tools/{specs,registry,impl,runner}.py` | schema-validated tool registry + runner with MCP/direct transports |
| MCP | `app/mcp/{server,client}.py` | real stdio MCP server (14 tools) + client |
| Retrieval | `app/services/scholarly/{openalex,crossref,arxiv,aggregator,dedupe,ranking,http,records}.py` | live APIs, parallel swarm, dedupe, ranking, retry/backoff, cache |
| Memory | `app/db/{models,base}.py`, `app/services/embeddings.py` | 17 tables, project-scoped retrieval, vectors |
| Runtime/governance | `app/runtime/runtime.py`, `app/services/{llm,health,text_analysis}.py`, `app/logging_conf.py` | step timing, retries, tracing, hash-chained audit log, Ollama client |
| UI | `frontend/src/App.tsx` + 9 tab components | project switcher, run panel, all evidence views |

## 3. Removed during the build

| Path | Why |
|---|---|
| `spike/{cli.py,cli2.py,srv.py,srv2.py}` | throw-away probes used to learn the `mcp` SDK wire format. Superseded by `app/mcp/server.py` and `tests/test_lab05_mcp.py`; keeping them would present unreachable code as part of the deliverable. |
| `frontend/vite.config.check.ts` | temporary config used to diagnose the TS build; build now verified with `npm run build`. |
| `frontend/dist` (stale) | replaced by `backend/static/ui`, so the SPA ships inside the API process (one origin, no CORS in production). |

No dead code was left registered-but-unused: `app/tools/specs.py` and the tool
`impl.py` handlers are 1:1 (`/api/system/tools` reports `registered: 14`, and
`tests/test_lab05_mcp.py::test_registry_and_mcp_expose_the_same_tools` asserts the
MCP server exposes exactly the same 14).

## 4. Duplication and structural findings

1. **Two frontends existed transiently** (`frontend/dist` and `backend/static/ui`).
   Resolved: single build output, and `app/main.py` resolves a candidate list
   (`backend/static/ui` first, then `frontend/dist`) so a stale local `dist/` can
   never silently shadow the fresh build.
2. **Retrieval was reachable from two places** (agents calling source adapters
   directly *and* agents calling tools). Resolved: agents always go through
   `ToolRunner`, which either proxies to the MCP subprocess or calls the same
   registry in-process — one code path, one audited `tool_invocations` record.
3. **Two "summary" shapes for a run** (`stats_json` written by the service and a
   per-agent dict). Resolved: `stats_json` is the only run summary; agents return
   partial state that the graph merges.
4. **Facade duplication in the LLM layer** (module-level singleton *and* an agent
   helper). Resolved: `app/services/llm.get_llm()` is the single accessor; agents
   import it from there (confirmed by `tests/test_llm_service.py` and the
   `fake_ollama` fixture patching that same symbol).

## 5. Known weaknesses (honest list)

| # | Finding | Impact | Mitigation in place |
|---|---|---|---|
| 1 | `app/api/workspace.py` is large (~600 lines, 6 resources) | harder to navigate | split is documented in doc 04; all handlers share one `deps.py` accessor pattern |
| 2 | Semantic search quality is lexical when Ollama embeddings are absent | weaker recall on paraphrased queries | the fallback is *labelled* in `discovery_stats.embedding.note` and in the UI; `nomic-embed-text` path is implemented |
| 3 | Method-family classification in Related Work is keyword-based | occasional mis-grouping ("statistical" for a CNN paper) | the section says so in a closing sentence; treated as a starting point, not a claim |
| 4 | Gap detection reads abstracts only | gaps cannot be validated without full text | warning emitted: "N of M papers had no abstract…" |
| 5 | No auth / multi-user tenancy | single local user by design | project isolation is enforced in every query; documented as a limitation (doc 10) |
| 6 | `pytest-asyncio` runs in strict-ish auto mode with function-scoped DB | slower suite (~20 s) | acceptable; `slow` and `live` markers let you narrow the run |
| 7 | Frontend has no component tests | UI regressions are caught by typecheck + manual pass | `npm run build` (tsc strict) is the gate; documented in doc 08 |
| 8 | Ollama is not installed in the verification environment | LLM prose paths are covered by mocked tests only | every UI/API surface reports `LLM unavailable` verbatim; live check in doc 08 |

## 6. Baseline metrics (measured)

| Metric | Value | How measured |
|---|---|---|
| Backend Python (app only) | 10 653 lines across 63 modules | `find app -name '*.py' | xargs wc -l` |
| Tests | 84 tests (80 offline + 4 live) in 17 modules | `pytest --collect-only`, `wc -l` |
| Frontend TS/TSX | 2 749 lines | `wc -l frontend/src/**` |
| REST operations | 37 on 32 paths | `app.openapi()['paths']` |
| DB tables | 17 | `Base.metadata.sorted_tables` |
| Registered tools | 14 | `GET /api/system/tools` → `registered: 14` |
| SPA bundle | 209 kB JS / 19.4 kB CSS (60.2 kB gzip JS) | `npm run build` |
