# 06 — Database Setup

## 1. Choice and rationale

**SQLite + SQLAlchemy 2.1 async (`aiosqlite`)**. Reasons:

* zero-install and file-based — a course marker can run the project without a server;
* the async driver keeps the whole request/workflow path non-blocking;
* every query is `await`-ed through the same `SessionLocal`, so moving to PostgreSQL
  is a one-line DSN change (no ORM code change; only the optional `asyncpg` driver);
* vectors are stored as JSON and scored in Python, so `pgvector` is **not** required.

PostgreSQL is supported if you want it: set
`DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/research` and
`pip install asyncpg`.

## 2. Creation

The database is created automatically on startup (`init_db()` in `app/main.py`,
`Base.metadata.create_all`). No migration tool is needed for a fresh install:

```bash
cd backend
python -c "import asyncio; from app.db.base import init_db; asyncio.run(init_db()); print('db ready')"
```

Files created:

```
backend/data/research.db          # main database
backend/data/research.db-wal      # SQLite write-ahead log (normal)
backend/exports/{project_id}/     # exported artefacts, one folder per project
```

Reset (destroys all projects — ask before running):

```bash
# PowerShell
Remove-Item backend/data/research.db* -Force
# bash
rm -f backend/data/research.db*
```

## 3. Schema — 17 tables

Generated from `Base.metadata.sorted_tables`; column lists are exact.

| Table | Columns | Role |
|---|---|---|
| `projects` | id, name, topic, domain, status, settings_json, created_at, updated_at | one research project; **isolation root** — every other table carries `project_id` |
| `workflow_runs` | id, project_id, topic, status, stage, config_json, stats_json, error, llm_available, created_at, finished_at | one execution of the agent graph |
| `papers` | id, project_id, run_id, dedupe_key, doi, arxiv_id, title, norm_title, authors_json, year, venue, abstract, url, pdf_url, cited_by, type, open_access, sources_json, source_queries_json, retrieved_at, rank_score, rank_explain_json, is_selected, user_note | retrieved records + provenance + ranking explanation |
| `paper_vectors` | id, project_id, paper_id, model, dim, vector_json, created_at | embedding per paper (`model` records which one) |
| `search_cache` | id, cache_key, source, payload_json, retrieved_at | source payload cache; **`retrieved_at` is the original fetch time**, which is what the UI shows |
| `source_attempts` | id, run_id, project_id, attempt_no, source, query, status, http_status, latency_ms, records, error, execution_mode, retrieved_at | per-source outcome (`ok / empty / error / timeout`), transport |
| `tool_invocations` | id, project_id, run_id, tool, transport, args_json, status, latency_ms, result_summary, error, created_at | every tool call, validated args, `mcp` or `direct` |
| `trace_events` | id, project_id, run_id, seq, agent, step, status, detail_json, duration_ms, created_at | agent-level steps with timing |
| `research_gaps` | id, project_id, run_id, title, description, rationale, evidence_paper_ids, evidence_quotes, kind, confidence, feasibility, suggested_metrics, generated_by, created_at | gaps; `evidence_paper_ids`/`evidence_quotes` make fabrication visible |
| `research_ideas` | id, project_id, run_id, title, research_questions, objectives, proposed_methodology, suggested_datasets, metrics, challenges, feasibility, supporting_paper_ids, generated_by, created_at | proposed studies tied to gaps |
| `drafts` | id, project_id, run_id, version, sections_json, markdown, status, generated_by, created_at, updated_at | versioned manuscripts; `status ∈ draft/approved/rejected` |
| `citation_reports` | id, project_id, run_id, report_json, checked, failed, created_at | audit results, including `claim_level_evidence_check` |
| `radar_results` | id, project_id, run_id, kind, name, payload_json, verification, source_url, retrieved_at | venues / funders / collaborators, each with a verification badge value |
| `collaborators` | id, project_id, run_id, name, author_key, works_count, relevant_papers, similarity, evidence_note, source_url, retrieved_at | people suggestions with the evidence that justifies them |
| `approvals` | id, project_id, run_id, artifact_type, artifact_id, gate, status, requested_at, decided_at, actor, note | the human-in-the-loop gate |
| `exports` | id, project_id, run_id, kind, filename, rel_path, size_bytes, approved_by, created_at | produced files + who approved |
| `audit_log` | id, project_id, seq, action, actor, payload_json, prev_hash, hash, created_at | append-only, hash-chained event log |

## 4. Integrity and isolation rules enforced in code

1. **Project scoping.** Every read path filters by `project_id`; there is no endpoint
   that returns another project's rows. Verified by
   `test_lab04_memory::test_papers_are_project_scoped` and
   `test_lab14_capstone_e2e::test_two_topics_produce_different_results_and_stay_isolated`.
2. **Dedupe.** `papers.dedupe_key` is unique per project (`doi:…`, `arxiv:…`, or
   `title:<normalised>`); a repeated retrieval increments nothing and reports
   `skipped_duplicates`.
3. **Cascade.** `workflow_runs` children (attempts, traces, tool calls) cascade on
   delete so a cancelled/deleted project leaves no orphans.
4. **Audit chain.** `audit_log.hash = sha256(prev_hash + seq + action + payload)`;
   `GET /api/projects/{id}/audit` recomputes the chain and returns
   `{valid, records, broken_at_seq, detail}`.
5. **No ORM lazy-loading surprises.** All relationships are loaded explicitly; the
   API returns plain dicts (`_serialize` helpers), which is why `.scalars()` +
   `list(...)` is the standard pattern in this codebase.

## 5. Measured state after the verification session

| Metric | Value |
|---|---|
| Projects | 3 (two demo + one live verification project) |
| Papers | 22 (road anomaly), 18 (federated learning), 14 (contrastive medical imaging) |
| Gaps / ideas / drafts | 2 / 2 / 1 per run |
| Audit records (latest project) | 13, `chain_verification: {'valid': True, 'broken_at_seq': None}` |
| Export rows (latest project) | 8 files, each with `approved_by` recorded |

Quick inspection without a client:

```bash
python - <<'PY'
import sqlite3, json
c = sqlite3.connect("data/research.db")
for t in ("projects", "papers", "research_gaps", "drafts", "exports", "audit_log"):
    print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
PY
```
