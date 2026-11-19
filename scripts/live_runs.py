"""Live acceptance driver — talks to a running backend over HTTP only.

Usage:
  python scripts/live_runs.py create          # create the three acceptance projects
  python scripts/live_runs.py run <slug>      # start a run and watch it to the end
  python scripts/live_runs.py status          # summarise every project's latest run
  python scripts/live_runs.py cancel <slug>   # start a run and cancel it mid-flight
  python scripts/live_runs.py isolation       # cross-project leakage check

No data is fabricated: everything printed comes from the API responses.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://localhost:8000"

TOPICS = [
    {
        "slug": "agri",
        "name": "Precision agriculture — crop yield prediction",
        "topic": "AI-driven precision agriculture for crop yield prediction",
        "domain": "auto",
        "research_instructions": (
            "Review the state of the art in AI/ML for crop yield prediction from precision-agriculture data. "
            "Focus on field-scale studies that combine remote sensing, weather and soil data with machine or deep "
            "learning. Prefer work from 2018 onwards, and prefer studies that report quantitative error metrics "
            "(RMSE, MAE, R2) on named datasets. Exclude pure remote-sensing classification papers that do not "
            "predict yield, and exclude opinion or policy pieces."
        ),
        "research_questions": [
            "Which sensor and data sources are used for crop yield prediction in precision agriculture?",
            "Which model families (statistical, classical ML, deep learning, hybrids) dominate and how are they evaluated?",
            "What are the main reported limitations, especially around generalisation across regions and seasons?",
        ],
    },
    {
        "slug": "blockchain",
        "name": "Blockchain digital identity and privacy-preserving authentication",
        "topic": "Blockchain-based digital identity with privacy-preserving authentication",
        "domain": "auto",
        "research_instructions": (
            "Survey decentralized and self-sovereign identity built on distributed ledgers, with an emphasis on "
            "privacy-preserving authentication: zero-knowledge proofs, verifiable credentials, selective disclosure "
            "and key management. Prioritise peer-reviewed work from 2019 onwards that reports concrete "
            "implementations, benchmarks or threat models. Exclude pure cryptocurrency market or token-economics "
            "papers."
        ),
        "research_questions": [
            "Which cryptographic mechanisms are used for privacy-preserving authentication in blockchain identity systems?",
            "How are self-sovereign identity and verifiable credentials implemented on distributed ledgers?",
            "What threat models, scalability limits and open problems are reported?",
        ],
    },
    {
        "slug": "battery",
        "name": "Battery recycling and second-life storage",
        "topic": "Sustainable battery recycling and second-life energy storage systems",
        "domain": "auto",
        "research_instructions": (
            "Review recycling routes for lithium-ion batteries (pyrometallurgical, hydrometallurgical, direct "
            "recycling) and the reuse of retired electric-vehicle packs as second-life stationary storage. Prefer "
            "studies with quantified recovery rates, cost or life-cycle-assessment results. Work from 2018 onwards. "
            "Exclude market-forecast and policy-only papers."
        ),
        "research_questions": [
            "Which recycling processes recover the most critical materials and at what cost?",
            "What is the technical and economic feasibility of second-life energy storage from retired EV batteries?",
            "What are the main sustainability trade-offs and data gaps?",
        ],
    },
]

RUN_CONFIG = {
    "result_limit": 20,
    "min_papers": 8,
    "generate_draft": True,
    "run_radar": True,
    "run_collaboration": True,
    "max_attempts": 2,
}


def call(method: str, path: str, body: dict | None = None, timeout: float = 120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        return {"__http_error__": e.code, "body": e.read().decode()[:400]}


def project_by_name() -> dict[str, dict]:
    return {p["name"]: p for p in call("GET", "/api/projects") or []}


def cmd_create() -> None:
    existing = project_by_name()
    for t in TOPICS:
        if t["name"] in existing:
            p = existing[t["name"]]
            print(f"= exists  {t['slug']:<10} {p['id']}  {p['name']}")
            continue
        p = call(
            "POST",
            "/api/projects",
            {
                "name": t["name"],
                "topic": t["topic"],
                "domain": t["domain"],
                "research_instructions": t["research_instructions"],
                "research_questions": t["research_questions"],
            },
        )
        if p.get("__http_error__"):
            print(f"! failed  {t['slug']}: {p}")
            continue
        print(f"+ created {t['slug']:<10} {p['id']}  domain={p.get('domain')}  chars(topic)={len(t['topic'])}")


def find_project(slug: str) -> dict | None:
    t = next(x for x in TOPICS if x["slug"] == slug)
    return project_by_name().get(t["name"])


def watch(run_id: str, timeout_s: int = 900, verbose: bool = True) -> dict:
    """Poll the run and print every real stage transition."""
    seen: dict[str, str] = {}
    t0 = time.time()
    last_status = None
    while time.time() - t0 < timeout_s:
        run = call("GET", f"/api/runs/{run_id}")
        if run.get("__http_error__"):
            print("!", run)
            return run
        for st in run.get("stages", []):
            if seen.get(st["key"]) != st["status"]:
                seen[st["key"]] = st["status"]
                if verbose:
                    dur = st.get("duration_ms")
                    print(
                        f"   [{time.time()-t0:6.1f}s] {st['key']:<16} {st['status']:<10}"
                        + (f" {dur:.0f}ms" if isinstance(dur, (int, float)) else "")
                    )
        if run["status"] != last_status:
            if verbose:
                print(f"   status -> {run['status']}")
            last_status = run["status"]
        if run["status"] not in {"pending", "running", "cancelling"}:
            return run
        time.sleep(2)
    print("! timed out waiting for the run")
    return call("GET", f"/api/runs/{run_id}")


def cmd_run(slug: str) -> None:
    p = find_project(slug)
    if not p:
        print("! project missing; run create first")
        return
    started = call("POST", f"/api/projects/{p['id']}/runs", RUN_CONFIG)
    if started.get("__http_error__"):
        print("! start failed:", started)
        return
    print(f"> run {started['id']} for {p['name']}")
    run = watch(started["id"])
    stats = run.get("stats") or {}
    cit = stats.get("citation_summary") or {}
    print(
        f"= {run['status']}  papers={stats.get('papers')}  gaps={stats.get('gaps')}  "
        f"ideas={stats.get('ideas')}  draft=v{stats.get('draft_version')}  "
        f"doi_verified={cit.get('doi_verified')}/{cit.get('references')}  "
        f"queries={len(stats.get('queries') or [])}"
    )
    done = sum(1 for s in run.get("stages", []) if s["status"] == "completed")
    skipped = sum(1 for s in run.get("stages", []) if s["status"] == "skipped")
    print(f"= stages completed={done} skipped={skipped} of {len(run.get('stages', []))}")
    if run.get("error"):
        print("= error:", run["error"])


def cmd_cancel(slug: str, after_s: float = 3.0) -> None:
    p = find_project(slug)
    if not p:
        print("! project missing; run create first")
        return
    started = call("POST", f"/api/projects/{p['id']}/runs", RUN_CONFIG)
    run_id = started["id"]
    print(f"> run {run_id} started; cancelling after {after_s}s")
    time.sleep(after_s)
    t0 = time.time()
    res = call("POST", f"/api/runs/{run_id}/cancel", {"reason": "acceptance test: cancel mid-flight"})
    print(f"= cancel request took {time.time()-t0:.2f}s -> {res}")
    run = call("GET", f"/api/runs/{run_id}")
    print("= final status:", run["status"])
    print("= error field:", run.get("error"))
    print("= cancel_reason:", (run.get("stats") or {}).get("cancel_reason"))
    print("= pending_artifacts:", (run.get("stats") or {}).get("pending_artifacts"))
    for st in run.get("stages", []):
        if st["status"] != "pending":
            print(f"   {st['key']:<16} {st['status']}")
    # idempotency
    again = call("POST", f"/api/runs/{run_id}/cancel", {"reason": "second time"})
    print("= second cancel:", again)
    task = call("GET", f"/api/projects/{p['id']}/runs")
    print("= project runs:", [(r["id"][:8], r["status"]) for r in task][:4])


def cmd_status() -> None:
    for p in call("GET", "/api/projects") or []:
        detail = call("GET", f"/api/projects/{p['id']}")
        runs = detail.get("runs", [])
        last = runs[0] if runs else None
        print(f"\n{p['name']}  [{p['id'][:8]}]  domain={p['domain']}")
        print(f"  papers={detail.get('paper_count')} gaps={detail.get('gap_count')} "
              f"ideas={detail.get('idea_count')} drafts={detail.get('draft_count')} runs={detail.get('run_count')}")
        if last:
            done = sum(1 for s in last.get("stages", []) if s["status"] == "completed")
            print(f"  last run {last['id'][:8]} {last['status']} stage={last['stage']} completed_stages={done}")
            print(f"  queries: {[q[:60] for q in (last.get('stats') or {}).get('queries', [])]}")
        plan = detail.get("query_plan") or {}
        print(f"  plan queries={len(plan.get('queries', []))} max_len={max((len(q) for q in plan.get('queries', [])), default=0)} "
              f"used_instructions={plan.get('used_instructions')} by={plan.get('generated_by')}")


def cmd_isolation() -> None:
    """No project may see another project's papers, gaps, ideas or drafts."""
    projects = call("GET", "/api/projects") or []
    ids = {p["id"]: p["name"] for p in projects}
    print("== project isolation check ==")
    ok = True
    seen_papers: dict[str, set[str]] = {}
    for pid, name in ids.items():
        papers = call("GET", f"/api/projects/{pid}/papers")["papers"]
        gaps = call("GET", f"/api/projects/{pid}/gaps")["gaps"]
        ideas = call("GET", f"/api/projects/{pid}/ideas")["ideas"]
        seen_papers[pid] = {p["id"] for p in papers}
        # every gap's evidence must belong to this project
        bad = 0
        for g in gaps:
            for ev in g.get("evidence", []):
                if ev["paper_id"] not in seen_papers[pid]:
                    bad += 1
        print(f"  {name[:44]:<44} papers={len(papers):>3} gaps={len(gaps):>2} ideas={len(ideas):>2} "
              f"foreign_evidence={bad}")
        ok = ok and bad == 0
    # identical DOI across projects is expected and fine; identical paper *rows* are the problem
    owners: dict[str, list[str]] = {}
    for pid, titles in seen_papers.items():
        for t in titles:
            owners.setdefault(t, []).append(pid)
    shared = {t: v for t, v in owners.items() if len(v) > 1}
    print(f"  paper rows visible in more than one project: {len(shared)}")
    print("RESULT:", "PASS" if ok and not shared else "FAIL")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "create":
        cmd_create()
    elif cmd == "run":
        cmd_run(arg)
    elif cmd == "cancel":
        cmd_cancel(arg, float(sys.argv[3]) if len(sys.argv) > 3 else 3.0)
    elif cmd == "isolation":
        cmd_isolation()
    else:
        cmd_status()
