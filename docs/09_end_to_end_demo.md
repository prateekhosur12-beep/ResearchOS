# 09 — End-to-End Demo (transcript of a real session)

Everything below is copied from an actual session on **2026-10-30** against the running
server with live network access and **no Ollama daemon** (so you can see exactly what the
honest-degradation path looks like). No numbers were edited.

Server: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`, UI served at `/`.
Machine: Python 3.13.16, Node 20.20.2, Ollama not installed.

---

## Step 0 — The system reports its own state

```
$ curl -s localhost:8000/api/health
{"status":"ok","app":"Agentic AI Research Assistant","version":"1.0.0","uptime_s":3.0}

$ curl -s localhost:8000/api/system/status   # abridged
llm:      {'available': False, 'model': 'qwen2.5:3b', 'models_installed': [],
           'detail': 'Cannot reach Ollama at http://localhost:11434 (ConnectError). Start it with: ollama serve'}
sources:  [('openalex','ok',818), ('crossref','ok',244), ('arxiv','ok',56)]
mcp:      {'ok': True, 'tool_count': 14,
           'server': {'name':'agentic-research-tools','version':'1.0.0','protocol_version':'2025-11-25'}}
transport:'mcp'
```

Three things worth noting: the LLM is **absent and says so**; the three scholarly APIs are
probed live (not assumed); the MCP server is a real subprocess that answered a protocol
handshake with 14 tools.

## Step 1 — Create a project with a specific topic

```
$ curl -s -X POST localhost:8000/api/projects -H 'Content-Type: application/json' \
    -d '{"name":"Contrastive Learning for Medical Imaging",
         "topic":"contrastive learning for medical image segmentation",
         "domain":"computer_science"}'
project_id = bb088c4d02784045b394cd995642d77a
```

## Step 2 — Run the agent workflow

```
$ curl -s -X POST localhost:8000/api/projects/$PID/runs -H 'Content-Type: application/json' \
    -d '{"result_limit":10,"min_papers":5,"generate_draft":true,
         "run_radar":true,"run_collaboration":true,"max_attempts":2}'
{"id":"2c22607619ea4f8c92e462579eadf651","status":"pending","stream":"/api/runs/2c22607619ea4f8c92e462579eadf651/events"}
```

25 s later (SSE events show each stage as it happens; the UI shows the same stream):

```
$ curl -s localhost:8000/api/runs/2c22607619ea4f8c92e462579eadf651
status: awaiting_approval      stage: finalize
tool_transport: mcp — "MCP stdio session to 'agentic-research-tools' (protocol 2025-11-25)"
queries: ['contrastive learning for medical image segmentation']
discovery: records_raw=15  unique=14  merged=1 (doi)  failed_sources=[]
  openalex  ok  5 records  670 ms  via mcp
  crossref  ok  5 records  284 ms  via mcp
  arxiv     ok  5 records  930 ms  via mcp
embedding: {indexed: 14, model: 'lexical-hash-v1',
            note: 'Ollama embedding model unavailable — using deterministic lexical hashing (similarity is lexical, not semantic)'}
stages: discovery → gap_analysis → deep_research → idea_generation → drafting →
        citation_audit → radar → collaboration → approval → finalize
warnings:
  - gaps derived deterministically from abstract text (LLM unavailable)
  - 5 of 14 papers had no abstract; their gaps could not be assessed from text. Retrieve full text before relying on them.
  - LLM unavailable: the report contains mechanical evidence summaries only, no prose synthesis
  - LLM unavailable — Cannot reach Ollama at http://localhost:11434 (ConnectError). Start it with: ollama serve
```

Trace: **7 agent steps, 26 tool invocations, all transport `mcp`**.

```
(1) LiteratureDiscoveryAgent.understand_topic      ok      0 ms
(2) GapAnalysisAgent.gap_analysis                  ok     43 ms
(3) DeepResearchAgent.deep_research                ok   1437 ms
(4) DraftingAgent.draft_manuscript                 ok     20 ms
(5) CitationComplianceAgent.citation_audit         ok    413 ms
(6) FundingJournalAgent.venue_and_funding_radar    ok   1667 ms
(7) CollaborationAgent.collaborator_search         ok    629 ms
```

## Step 3 — The retrieved literature is real and topic-specific

```
$ curl -s localhost:8000/api/projects/$PID/papers
count 14
 - 2026 | Pixel-level Counterfactual Contrastive Learning for Medical Image Segmentation        | openalex
 - 2024 | Class-aware Patch Based Contrastive Learning for Medical Image Segmentation           | openalex
 - 2024 | A Medical Image Segmentation Method Combining Knowledge Distillation and Contrastive… | crossref
 - 2025 | Stronger is not better: Better Augmentations in Contrastive Learning for Medical Ima… | openalex
 - 2021 | Learning With Context Feedback Loop for Robust Medical Image Segmentation              | arxiv
 - 2023 | Weakly-Supervised 3D Medical Image Segmentation using Geometric Prior and Contrastive… | arxiv
```

The other project in the same database (topic *road anomaly detection*) holds a completely
different corpus — **no overlap**:

```
count 22
 - 2025 | Explainable Road Scene Anomaly Detection Using VGG 16 and XAI … | openalex,crossref
 - 2024 | YOLO based road anomaly detection for Indian roads             | openalex
 - 2025 | An Advanced Approach for Road Anomaly Detection with Transfer Learning Using YOLO…  | openalex,crossref
 - 2025 | AVD-YOLO: Active Vision-Driven Multi-Scale Feature Extraction …  | crossref
```

## Step 4 — Gaps carry verbatim evidence

```
$ curl -s localhost:8000/api/projects/$PID/gaps
count 2

1) kind=evidence_backed  confidence=0.65
   title: Data and dataset constraints reported by the studies — "These limitations are even
          more pronounced given the volumetry of medical imaging data"
   rationale: Direct evidence: the quoted sentences are the authors' own words.
   evidence:
     - 4b109c7b…  "Building medical image classifiers with very limited data using segmentation networks" (2018)
       quote: "Deep learning has shown promising results in medical image analysis, however, the lack of
               very large annotated datasets confines its full potential."
     - 02f082c1…  "Cross-dimensional transfer learning in medical image segmentation with deep learning" (2023)
       quote: "These limitations are even more pronounced given the volumetry of medical imaging data."
```

The second gap is labelled `kind=hypothesis` (a cross-paper pattern, not a direct quote) —
the distinction is explicit in the data model and in the UI.

## Step 5 — Research ideas, draft, and citations

Ideas (2) each carry RQs, objectives, proposed methodology, datasets, metrics, challenges,
feasibility and `supporting_paper_ids`.

Draft v1 (IEEE style, 12 references, 11 771 chars) — opening verbatim:

```markdown
# Addressing data and dataset constraints reported by the studies — "these limitations are
  even more pronounced given the volumetry of medical imaging data" in contrastive learning
  for medical image segmentation

> **Draft generated by the Agentic AI Research Assistant** · 2026-10-30 · topic: *contrastive learning for medical image segmentation*
>
> This is a literature-grounded **proposal draft**. No experiments were executed and no
> empirical results are claimed. Every citation refers to a record retrieved by this
> project; unverified fields are marked in the citation audit.
```

Citation audit (recomputed on demand):

```
POST /api/projects/$PID/citations/audit  ->
{"references": 12, "in_text_markers": 12, "doi_verified": 11, "doi_failed": 0,
 "doi_unavailable": 1, "missing_bibliography_entries": [], "unused_bibliography_entries": [],
 "duplicates": [], "entries_with_issues": 1}
claim_level_evidence_check: "not_evaluated"
```

`doi_unavailable` means "this record has no DOI to check" (an arXiv-only or OA-only record),
which is different from `doi_failed` ("a DOI exists but did not resolve"). The report states
that DOI verification proves the *metadata resolves* — not that the source supports the claim.

## Step 6 — Venues, funding, people (all verified against registries, none invented)

```
JOURNAL  Pattern Recognition                       | verification: verified  | publisher: Elsevier | ISSN present
JOURNAL  International Joint Conference on Neural Networks (IJCNN) | verification: unverified
JOURNAL  arXiv (Cornell University)                | verification: unverified

FUNDING  Engineering and Physical Sciences Research Council | ror: https://ror.org/0439y7842
         award_ids: ["EP/Y028856/1", "EP/R0…"]
FUNDING  Basic and Applied Basic Research Foundation of Guangdong Province
         openalex_id: https://openalex.org/F4320337111 | award_ids: ["2021A151501131…"]

COLLAB   Yiyu Shi                  | 6 papers in corpus | similarity 0.24
         "6 paper(s) in the retrieved set on this exact query; topic overlap is measured by
          co-occurrence in those records."
```

Disclaimers returned with the payload and displayed in the UI:

```
venues:        "Verified = title/ISSN/publisher confirmed in the Crossref journal registry.
                Impact factor and acceptance rate are not available from these sources."
funding:       "Funders and award IDs are those recorded on real publications, plus OpenAlex
                funder entities. No deadlines, amounts or eligibility are claimed."
collaboration: "Candidates are real authors of retrieved records. Similarity ≠ availability."
```

## Step 7 — The approval gate is real (HTTP 403, server-side)

```
$ curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/projects/$PID/exports \
    -H 'Content-Type: application/json' -d '{"kind":"manuscript_md"}'
403
{"detail":"This artefact requires human approval before export. Submit the draft for
 approval and approve it first (POST /projects/{id}/approvals)."}

# papers_csv is not gated, and correctly still works:
papers_csv HTTP 200  contrastive-learning-for-medical-imaging_papers_csv_20261030_033005.csv  4200 B
```

The decide endpoint validates strictly (this exact mistake was made during the session and
the API rejected it):

```
POST /api/approvals/{id}/decide {"decision":"approve"} -> 422
  "msg": "Input should be 'approved' or 'rejected'"

POST /api/approvals/{id}/decide {"decision":"approved","actor":"course-instructor",
                                 "note":"Reviewed against retrieved sources."}
{"ok":true,"approval_id":"422346c6…","status":"approved"}
```

## Step 8 — Exports after approval (real files on disk)

| kind | HTTP | bytes | file |
|---|---|---|---|
| `manuscript_md` | 200 | 11 771 | `contrastive-learning-for-medical-imaging_manuscript_md_20261030_033010.md` |
| `manuscript_docx` | 200 | 40 980 | `…_manuscript_docx_20261030_033010.docx` |
| `full_report_md` | 200 | 24 015 | `…_full_report_md_20261030_033010.md` |
| `citations_csv` | 200 | 1 786 | `…_citations_csv_20261030_033011.csv` |
| `radar_md` | 200 | 3 728 | `…_radar_md_20261030_033011.md` |
| `gaps_md` | 200 | 2 717 | `…_gaps_md_20261030_033011.md` |
| `papers_md` | 200 | 2 888 | `…_papers_md_20261030_033011.md` |
| `citations_md` | 200 | 2 232 | `…_citations_md_20261030_033011.md` |
| `papers_csv` | 200 | 4 200 | `…_papers_csv_20261030_033005.csv` |

Files live in `backend/exports/<project_id>/`; each `exports` row records `approved_by`.

## Step 9 — The audit chain

```
$ curl -s localhost:8000/api/projects/$PID/audit
chain_verification: {'valid': True, 'records': 13, 'broken_at_seq': None, 'detail': 'chain intact'}
actions: run_started, approval_requested, run_finished, export_created,
         approval_approved, export_created ×8
```

## Step 10 — What the same session looks like in the UI

Because the sandbox browser cannot reach `localhost`, the UI is described by its behaviour
against these same endpoints (tabs map 1:1 to the API calls above):

* **Overview** — 14 papers / 2 gaps / 2 ideas / draft v1, a pending-approval banner linking
  to Draft, the run card (queries, `mcp` transport, 15 raw → 14 unique, failed sources),
  collapsible warnings (the three honesty strings above), and the stage log.
* **Literature** — sortable table with source chips (`openalex`, `crossref`, `arxiv`),
  original `retrieved_at`, ranking explanation, in-project semantic search box.
* **Gaps & Ideas** — each gap expands to show the quoted sentences and the paper they came
  from; the deep-research report renders inline.
* **Draft** — section-by-section Markdown, `generated_by` per section, regenerate button,
  approve/reject with an actor name.
* **Citations** — colour-coded verification per entry, `doi_verified / doi_failed /
  doi_unavailable` counters, one-click re-audit.
* **Venues·Funding·People** — verification badges that are never upgraded beyond what the
  registry returned, award IDs, and the three disclaimers.
* **Trace & Audit** — 7 steps with durations, 26 tool invocations labelled `mcp`, three
  source attempts with latency, and the hash-chain badge.
* **Exports** — 9 kinds, the 403 rule explained in place, previous exports with
  `approved_by` and download links.
* **System** — re-probe button, "LLM offline" banner with the exact reason, per-source
  status, MCP protocol/tool count, redacted config, Labs 1–14 mapping table.

## Step 11 — Two topics, two different worlds (the acceptance test)

| | contrastive learning for medical image segmentation | road anomaly detection using YOLO |
|---|---|---|
| papers stored | 14 | 22 |
| top hit | *Pixel-level Counterfactual Contrastive Learning for Medical Image Segmentation* (2026) | *Explainable Road Scene Anomaly Detection Using VGG 16 and XAI* (2025) |
| gap theme | data/dataset constraints in medical imaging | cross-city generalisation of detectors |
| venues | Pattern Recognition, IJCNN, arXiv | IEEE Access, Sensors, arXiv |
| draft size | 11 771 chars | ~12 000 chars |
| shared rows | **0** | **0** |

Repeatable in one command: `python smoke_e2e.py "<your topic>"` → 15/15 checks.
