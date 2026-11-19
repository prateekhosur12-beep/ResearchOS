# 10 — Known Limitations

This list is deliberately uncomfortable. Each item states what is weak, why, what the
system does about it, and how you can check it yourself.

## A. Model / LLM

1. **No local model was available in the verified environment.** Every recorded result in
   docs 08–09 was produced with Ollama *absent*. The LLM paths exist and are unit-tested
   against a mocked transport, but model-written prose quality has **not** been verified on
   this machine. The system never pretends otherwise: `llm.available=false`, the UI shows
   "LLM offline" with the exact reason, and agents fall back to `generated_by="heuristic"`.
   *Check:* `curl localhost:8000/api/system/status` → `llm.detail`.
2. **The fallback prose is mechanical.** Section templates are assembled from retrieved
   abstracts, so the manuscript is a literature-grounded *proposal skeleton*, not a
   publishable review. It says so in its own header ("No experiments were executed and no
   empirical results are claimed").
3. **`qwen2.5:3b` is small.** Even when installed, expect weaker synthesis and occasional
   JSON-schema failures; the client repairs once, then falls back and reports
   `LLM output failed output validation`.
4. **Embeddings require a second model.** `nomic-embed-text` must be pulled separately.
   Without it, `local_embed()` uses deterministic lexical hashing — similarity is
   *lexical*, which is labelled in the response and the UI. Paraphrase-level recall is
   therefore limited.
5. **No claim-level entailment.** The citation audit verifies that a DOI resolves and that
   markers match the bibliography. It cannot verify that a source *supports* the sentence
   citing it; the report states `claim_level_evidence_check: "not_evaluated"`.

## B. Retrieval and evidence

6. **Abstracts are often missing.** In the recorded runs 5 of 14–22 papers had no abstract
   (OpenAlex `abstract_inverted_index: null`, Crossref `abstract: null`). Gaps can only be
   derived from text, so those papers contribute ranking and citation entries but no gap
   evidence. The exact count is emitted as a warning every run.
7. **Full text is never fetched.** Only metadata and abstracts are used; no PDF parsing, no
   section-level retrieval, no table extraction.
8. **Three sources only.** OpenAlex, Crossref, arXiv. No Scopus/WoS/PubMed/Semantic Scholar,
   so coverage is biased toward open metadata and CS/Physics preprints.
9. **Query quality is bounded.** The discovery loop tries at most 3 query formulations
   (configurable). Niche or multi-word-domain topics can return few relevant records; the
   run then proceeds with what it has and reports `target_met=false`.
10. **Dedupe is heuristic.** DOI → arXiv id → normalised title. Preprints that were later
    published under a different title may appear twice; version-level merging is not done.
11. **Ranking is a transparent heuristic** (relevance + recency + citations), not a learned
    ranker. The weights are visible in `rank_explain_json`.
12. **Method-family grouping in Related Work is keyword-based** and therefore sometimes
    wrong (a segmentation paper mentioning "statistical analysis" can be filed under
    "statistically-driven work"). The section says the grouping is mechanical.

## C. Domain and integrity

13. **Two domain packs only** (computer science, generic). Other disciplines get the generic
    pack; domain-specific review criteria are not implemented.
14. **Venue verification is title-similarity based.** Only a near-exact match (≥0.92) against
    the Crossref *journal* registry is reported as `verified`. Conference proceedings and
    books usually have no journal record and are correctly shown as `unverified` — but a
    journal with an unusual title can also fail the threshold. Impact factor, acceptance
    rate and deadlines are never produced because these sources don't provide them.
15. **Funder data is sparse.** Only works that carry funder metadata contribute; OpenAlex
    funder entities are matched by name. No calls, deadlines, amounts or eligibility.
16. **Collaborator similarity ≠ availability.** It is co-occurrence in the retrieved corpus.
    The UI prints `Similarity ≠ availability`.

## D. Engineering

17. **Single user, no authentication.** Anyone who can reach the port can act. TLS, accounts
    and per-user permissions are out of scope for the lab; project isolation is enforced at
    the query level, not by credential.
18. **SQLite concurrency limits.** WAL mode is used, but many simultaneous runs would
    contend on writes; PostgreSQL is supported through `DATABASE_URL` but not load-tested.
19. **Vectors are JSON + Python cosine.** Fine for thousands of papers per project, not for
    millions; no ANN index (`pgvector`/FAISS) is wired in.
20. **Background runs live in the API process.** A crash mid-run leaves the run row in
    `running` with no worker to resume it; there is no durable queue, retry-after-restart or
    distributed execution.
21. **SSE is single-process** (in-memory pub/sub). Multiple workers would each see only
    their own runs' events.
22. **Rate limits.** With `SCHOLARLY_CONCURRENCY=4` and no caching benefit on new queries, a
    burst of projects can hit provider limits (HTTP 429). Retry/backoff handles it, but the
    run takes longer and the failure is reported rather than hidden.
23. **Export gate is policy, not cryptography.** The 403 is enforced server-side on
    `kind ∈ {manuscript_md, manuscript_docx, full_report_md}`; a direct database edit could
    bypass it. The audit chain makes such a change detectable, not impossible.
24. **Test coverage gaps.** No browser/E2E UI automation, no load tests, and live-API tests
    are opt-in (`RUN_LIVE_TESTS=1`) because they depend on the internet.
25. **`DEMO_MODE` exists but is not used by the product.** It is reserved for explicitly
    labelled synthetic testing; leaving it at `0` is required for real work.

## E. What the system deliberately refuses to do

* invent a paper, DOI, author, venue, funder, deadline, acceptance rate or result;
* present an LLM answer as evidence when the model is unavailable;
* claim a lab is finished because a UI panel exists;
* mark a failed source, step or export as successful;
* report a composite "trust score" that hides which check failed.

If you find a place where it does one of these, that is a bug, and the trace tables
(`tool_invocations`, `source_attempts`, `trace_events`, `audit_log`) are where to prove it.
