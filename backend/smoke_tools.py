"""Smoke test: real MCP session -> live scholarly search. No mocks."""
import asyncio
import sys
import time

sys.path.insert(0, "/home/user/backend")

from app.db.base import init_db, dispose_engine
from app.tools.runner import ToolRunner


async def main():
    await init_db()
    runner = ToolRunner(record=False, transport="mcp")
    await runner.start()
    print("TRANSPORT:", runner.mode, "|", runner.transport_note)

    t0 = time.perf_counter()
    res = await asyncio.gather(
        runner.call("search_openalex", {"query": "road anomaly detection YOLO", "limit": 4}),
        runner.call("search_crossref", {"query": "road anomaly detection YOLO", "limit": 4}),
        runner.call("search_arxiv", {"query": "road anomaly detection YOLO", "limit": 4}),
    )
    print("PARALLEL WALL: %.2fs" % (time.perf_counter() - t0))
    for r in res:
        print(f"  {r.get('tool')}: status={r.get('status')} count={r.get('count')} "
              f"latency={r.get('latency_ms')}ms err={r.get('error')}")
        for rec in (r.get("records") or [])[:2]:
            print("     -", rec["title"][:90], "|", rec.get("year"), "|", (rec.get("doi") or rec.get("arxiv_id")))

    bad = await runner.call("search_openalex", {"query": "", "limit": 5})
    print("VALIDATION:", bad.get("status"), bad.get("error", "")[:100])

    txt = await runner.call("read_research_file", {"rel_path": "../../etc/passwd"})
    print("TRAVERSAL BLOCKED:", txt.get("ok"), txt.get("error"))

    await runner.aclose()
    await dispose_engine()


asyncio.run(main())
