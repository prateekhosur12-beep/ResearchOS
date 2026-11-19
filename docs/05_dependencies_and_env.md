# 05 — Dependencies and Environment Configuration

## 1. Runtime requirements

| Component | Required | Verified here |
|---|---|---|
| Python | 3.11+ (uses `X | None` typing, `asyncio.TaskGroup`-style patterns) | **3.13.16** |
| Node.js | 18+ (Vite 5 / React 18) | **v20.20.2** (npm 10.8.2) |
| Ollama | optional but recommended for LLM prose | **not installed** in the verification sandbox → the app reported `LLM unavailable` and used its deterministic paths |
| Disk | ~150 MB (node_modules) + DB and exports | — |
| Network | outbound HTTPS to `api.openalex.org`, `api.crossref.org`, `export.arxiv.org` | reachable (verified) |

## 2. Python packages (`backend/requirements.txt`, pinned to the versions used)

| Package | Version | Why |
|---|---|---|
| `fastapi` | 0.162.0 | API framework |
| `uvicorn[standard]` | 0.54.0 | ASGI server |
| `pydantic` | 2.14.1 | request/response + tool schemas |
| `pydantic-settings` | 2.16.2 | env-based configuration |
| `SQLAlchemy` | 2.1.6 | async ORM (2.0/2.1 style `Mapped[]`) |
| `aiosqlite` | 0.22.1 | async SQLite driver |
| `greenlet` | 3.5.6 | required by SQLAlchemy's async bridge |
| `httpx` | 0.28.1 | scholarly APIs + Ollama client |
| `python-docx` | 1.1.2 | `.docx` manuscript export |
| `python-multipart` | 0.0.32 | form uploads (future) |
| `langgraph` | 1.2.18 | agent node graph |
| `typing-extensions` | latest | LangGraph requirement |
| `mcp` | 2.3.0 | MCP stdio server + client |
| `pytest` | 9.0.3 | test runner |
| `pytest-asyncio` | 1.4.1 | async tests (`asyncio_mode = auto`) |
| `anyio` | 4.15.1 | httpx/pytest backend |

No `pgvector`, no `asyncpg`, no vector database server: embeddings are stored as
JSON vectors in SQLite and scored with cosine similarity in Python
(`app/services/embeddings.py`).

## 3. Frontend packages (`frontend/package.json`)

Runtime: `react@18.3.1`, `react-dom@18.3.1`.
Build/dev: `vite@5.4.11`, `@vitejs/plugin-react@4.3.4`, `typescript@5.6.3`,
`tailwindcss@3.4.17`, `postcss@8.4.49`, `autoprefixer@10.4.20`, `@types/react@18.3.12`,
`@types/react-dom@18.3.1`.

Scripts: `npm run dev` (Vite dev server on :5173, proxies `/api` → :8000),
`npm run build` (`tsc -b && vite build` → `../backend/static/ui`), `npm run typecheck`.

## 4. Environment variables (`backend/.env`)

Copy `backend/.env.example` → `backend/.env`. Every value below has a working default,
so the app also runs with no `.env` at all.

### Language model

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | only Ollama is supported |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | daemon endpoint |
| `OLLAMA_MODEL` | `qwen2.5:3b` | chat model |
| `OLLAMA_TIMEOUT` | `180` | seconds per generation |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | **separate** model; a chat model cannot emit vectors |
| `OLLAMA_EMBED_ENABLED` | `1` | `0` forces the deterministic lexical fallback |

When the daemon is unreachable the app does **not** substitute fake text: it records
`llm_available=false`, shows *"Cannot reach Ollama at http://localhost:11434
(ConnectError). Start it with: ollama serve"* in the UI, and every generative agent
returns `generated_by="heuristic"` with an explicit warning.

### Storage

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/research.db` | async DSN; PostgreSQL also works |
| `DATA_DIR` | `./data` | DB folder, ensures the directory exists |
| `EXPORT_DIR` | `./exports` | generated files, one subfolder per project |

### Scholarly sources

| Variable | Default | Meaning |
|---|---|---|
| `SCHOLARLY_CONTACT_EMAIL` | `student@example.edu` | polite-pool `mailto` sent to OpenAlex/Crossref |
| `OPENALEX_BASE_URL` | `https://api.openalex.org` | |
| `CROSSREF_BASE_URL` | `https://api.crossref.org` | |
| `ARXIV_BASE_URL` | `https://export.arxiv.org/api` | |
| `SCHOLARLY_TIMEOUT` | `25` | per-request timeout (s) |
| `SCHOLARLY_MAX_RETRIES` | `2` | retries on 429/5xx only |
| `SCHOLARLY_CONCURRENCY` | `4` | max parallel requests |

**Set a real contact e-mail.** Both OpenAlex and Crossref ask for it, and the polite
pool gives you higher rate limits. It is sent as a query parameter, never as a secret.

### Workflow policy

| Variable | Default | Meaning |
|---|---|---|
| `MIN_PAPERS_FOR_ANALYSIS` | `5` | target for the discovery loop; below it the agent revises the query |
| `DEFAULT_RESULT_LIMIT` | `20` | records per run |
| `MAX_RESULT_LIMIT` | `50` | hard cap, validated at the API |
| `MAX_DISCOVERY_ATTEMPTS` | `3` | bound of the Lab 1 loop |
| `MAX_GRAPH_REVISIONS` | `2` | bound of both graph loops (Lab 7) |
| `SEARCH_CACHE_TTL_SECONDS` | `86400` | cached source payloads; the original retrieval time is preserved and displayed |
| `REQUIRE_APPROVAL_BEFORE_EXPORT` | `1` | keeps the HTTP 403 gate on |

### MCP

| Variable | Default | Meaning |
|---|---|---|
| `MCP_ENABLED` | `1` | `1` = tools run through the stdio MCP server, `0` = same registry in-process |
| `MCP_SERVER_MODULE` | `app.mcp.server` | module executed as the subprocess |
| `MCP_CALL_TIMEOUT` | `90` | per tool call |

### Server

| Variable | Default | Meaning |
|---|---|---|
| `CORS_ORIGINS` | `*` | configured for the preview proxy; restrict in production |
| `LOG_LEVEL` | `INFO` | JSON logs |
| `DEMO_MODE` | `0` | **must stay 0** for real work; `1` is an explicitly labelled synthetic mode used only by tests |

## 5. Verifying the environment

```bash
cd backend
python -c "import fastapi, sqlalchemy, langgraph, mcp, httpx, docx; print('deps ok')"
python -m app.mcp.server --selftest     # prints tool count if it starts (Ctrl-C to exit)
curl -s localhost:8000/api/system/status | python -m json.tool
```

`/api/system/status` is the single source of truth for runtime state: LLM availability
(with the reason), each source's live probe and latency, MCP protocol version and tool
count, and a **redacted** config snapshot (secrets are never included — asserted in
`tests/test_lab10_resilience.py`).
