"""Tool implementations shared by the direct registry and the MCP server.

Every function here is deterministic given its inputs and the live scholarly APIs.
No tool invents records: when a source fails, the failure is returned as data.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import Draft, Paper, Project, ResearchGap, WorkflowRun
from app.logging_conf import get_logger
from app.services.scholarly import arxiv, crossref, openalex
from app.services.scholarly.dedupe import deduplicate
from app.services.scholarly.records import ScholarlyRecord, normalize_title
from app.tools.specs import (
    CompareInput,
    DoiInput,
    MemoryInput,
    ReadFileInput,
    ReportInput,
    SaveResultsInput,
    SearchAllInput,
    SearchInput,
)

log = get_logger("tools")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _search_payload(query: str, records: list[ScholarlyRecord], fetch: Any) -> dict[str, Any]:
    return {
        "tool": "search",
        "query": query,
        "status": fetch.status if fetch else ("ok" if records else "empty"),
        "http_status": getattr(fetch, "http_status", None),
        "latency_ms": getattr(fetch, "latency_ms", 0),
        "attempts": getattr(fetch, "attempts", 1),
        "error": getattr(fetch, "error", None),
        "retrieved_at": _now(),
        "records": [r.as_dict() for r in records],
        "count": len(records),
    }


async def search_openalex(payload: dict[str, Any]) -> dict[str, Any]:
    req = SearchInput.model_validate(payload)
    records, fetch = await openalex.search(
        req.query, req.limit, req.year_from, req.year_to, req.types or None
    )
    out = _search_payload(req.query, records, fetch)
    out["tool"] = "search_openalex"
    out["source"] = "openalex"
    return out


async def search_crossref(payload: dict[str, Any]) -> dict[str, Any]:
    req = SearchInput.model_validate(payload)
    records, fetch = await crossref.search(
        req.query, req.limit, req.year_from, req.year_to, req.types or None
    )
    out = _search_payload(req.query, records, fetch)
    out["tool"] = "search_crossref"
    out["source"] = "crossref"
    return out


async def search_arxiv(payload: dict[str, Any]) -> dict[str, Any]:
    req = SearchInput.model_validate(payload)
    records, fetch = await arxiv.search(
        req.query, req.limit, req.year_from, req.year_to, req.types or None
    )
    out = _search_payload(req.query, records, fetch)
    out["tool"] = "search_arxiv"
    out["source"] = "arxiv"
    return out


async def search_all_sources(payload: dict[str, Any]) -> dict[str, Any]:
    """In-server fan-out. Agents normally run the swarm client-side (Lab 8);
    this composite tool is exposed for MCP clients that want one call."""
    import asyncio

    req = SearchAllInput.model_validate(payload)

    async def one(fn, source):
        try:
            records, fetch = await fn(
                req.query, req.limit, req.year_from, req.year_to, req.types or None
            )
            return source, _search_payload(req.query, records, fetch)
        except Exception as exc:  # noqa: BLE001
            return source, {
                "tool": f"search_{source}",
                "source": source,
                "query": req.query,
                "status": "error",
                "error": f"{exc.__class__.__name__}: {exc}",
                "records": [],
                "count": 0,
                "retrieved_at": _now(),
            }

    pairs = await asyncio.gather(
        one(openalex.search, "openalex"),
        one(crossref.search, "crossref"),
        one(arxiv.search, "arxiv"),
    )
    all_records: list[ScholarlyRecord] = []
    sources = []
    for source, res in pairs:
        sources.append({k: v for k, v in res.items() if k != "records"})
        from app.services.scholarly.aggregator import record_from_dict

        all_records.extend(record_from_dict(r) for r in res.get("records") or [])
    merged, stats = deduplicate(all_records)
    return {
        "tool": "search_all_sources",
        "query": req.query,
        "sources": sources,
        "merged": [r.as_dict() for r in merged],
        "raw_count": len(all_records),
        "unique_count": len(merged),
        "dedupe": stats,
        "retrieved_at": _now(),
    }


async def lookup_doi(payload: dict[str, Any]) -> dict[str, Any]:
    req = DoiInput.model_validate(payload)
    record, fetch = await crossref.lookup_doi(req.doi)
    checked_with = "crossref"
    if record is None:
        record, fetch = await openalex.lookup_doi(req.doi)
        checked_with = "openalex"
    return {
        "tool": "lookup_doi",
        "doi": req.doi,
        "found": record is not None,
        "checked_with": checked_with,
        "status": fetch.status,
        "http_status": fetch.http_status,
        "error": fetch.error,
        "record": record.as_dict() if record else None,
        "retrieved_at": _now(),
    }


async def get_paper_details(payload: dict[str, Any]) -> dict[str, Any]:
    res = await lookup_doi(payload)
    res["tool"] = "get_paper_details"
    return res


async def compare_papers(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic comparison from the supplied records only (no invention)."""
    req = CompareInput.model_validate(payload)
    rows = []
    for p in req.papers:
        abstract = p.abstract or ""
        rows.append(
            {
                "id": p.id,
                "title": p.title,
                "year": p.year,
                "venue": p.venue,
                "doi": p.doi,
                "sources": p.sources or ([p.source] if p.source else []),
                "has_abstract": bool(abstract),
                "abstract_words": len(abstract.split()) if abstract else 0,
                "cited_by": p.cited_by,
                "method_signals": _method_signals(p.title, abstract),
                "limitation_sentences": _limitation_sentences(abstract),
                "datasets": _dataset_mentions(f"{p.title} {abstract}"),
            }
        )
    years = [r["year"] for r in rows if r["year"]]
    venues = sorted({r["venue"] for r in rows if r["venue"]})
    return {
        "tool": "compare_papers",
        "topic": req.topic,
        "count": len(rows),
        "rows": rows,
        "summary": {
            "year_range": [min(years), max(years)] if years else None,
            "distinct_venues": venues[:15],
            "papers_with_abstract": sum(1 for r in rows if r["has_abstract"]),
            "papers_with_limitations": sum(1 for r in rows if r["limitation_sentences"]),
            "note": "Signals are extracted from the supplied title/abstract text only.",
        },
    }


METHOD_KEYWORDS = {
    "survey": ["survey", "review", "overview"],
    "transformer": ["transformer", "attention", "bert", "gpt"],
    "cnn": ["cnn", "convolutional", "resnet", "yolo"],
    "federated": ["federated", "privacy-preserving"],
    "reinforcement": ["reinforcement", "policy gradient", "q-learning"],
    "rag": ["retrieval-augmented", "retrieval augmented", "rag"],
    "gnn": ["graph neural", "gnn", "graph convolution"],
    "benchmark": ["benchmark", "evaluation", "experiment"],
    "llm": ["large language model", "llm", "foundation model"],
    "diffusion": ["diffusion model", "stable diffusion"],
}


def _method_signals(title: str, abstract: str) -> list[str]:
    text = f"{title} {abstract}".lower()
    return [name for name, kws in METHOD_KEYWORDS.items() if any(k in text for k in kws)]


def _dataset_mentions(text: str) -> list[str]:
    """Named datasets/corpora mentioned in the supplied text (no invention)."""
    from app.services.text_analysis import extract_datasets

    return extract_datasets(text)


LIMIT_MARKERS = [
    "limitation",
    "limited to",
    "future work",
    "we do not",
    "does not address",
    "remains challenging",
    "constrain",
    "drawback",
    "shortcoming",
]


def _limitation_sentences(abstract: str) -> list[str]:
    if not abstract:
        return []
    sentences = [s.strip() for s in abstract.replace("\n", " ").split(". ") if s.strip()]
    return [s for s in sentences if any(m in s.lower() for m in LIMIT_MARKERS)][:4]


async def retrieve_project_memory(payload: dict[str, Any]) -> dict[str, Any]:
    """Persistent project memory: topic, stored papers, gaps, drafts (Lab 4)."""
    req = MemoryInput.model_validate(payload)
    async with SessionLocal() as session:
        project = await session.get(Project, req.project_id)
        if project is None:
            return {"tool": "retrieve_project_memory", "found": False, "error": "project not found"}
        papers = (
            await session.execute(
                select(Paper)
                .where(Paper.project_id == req.project_id)
                .order_by(Paper.rank_score.desc())
                .limit(req.limit)
            )
        ).scalars().all()
        gaps = (
            await session.execute(
                select(ResearchGap).where(ResearchGap.project_id == req.project_id).limit(req.limit)
            )
        ).scalars().all()
        drafts = (
            await session.execute(
                select(Draft)
                .where(Draft.project_id == req.project_id)
                .order_by(Draft.version.desc())
                .limit(3)
            )
        ).scalars().all()
        total = (
            await session.execute(
                select(func.count(Paper.id)).where(Paper.project_id == req.project_id)
            )
        ).scalar_one()
        runs = (
            await session.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == req.project_id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(5)
            )
        ).scalars().all()

    matches = papers
    semantic: dict[str, Any] | None = None
    if req.query:
        from app.services.embeddings import semantic_search

        async with SessionLocal() as session:
            semantic = await semantic_search(session, req.project_id, req.query, limit=req.limit)
        ids = [r["paper_id"] for r in semantic.get("results", [])]
        if ids:
            matches = [p for p in papers if p.id in ids] or papers

    return {
        "tool": "retrieve_project_memory",
        "found": True,
        "project": {
            "id": project.id,
            "name": project.name,
            "topic": project.topic,
            "domain": project.domain,
            "status": project.status,
        },
        "paper_count": total,
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "year": p.year,
                "doi": p.doi,
                "url": p.url,
                "abstract": (p.abstract or "")[:1200] or None,
                "sources": p.sources_json,
                "retrieved_at": p.retrieved_at.isoformat() if p.retrieved_at else None,
            }
            for p in matches
        ],
        "gaps": [{"id": g.id, "title": g.title, "kind": g.kind} for g in gaps],
        "drafts": [
            {"id": d.id, "version": d.version, "status": d.status, "generated_by": d.generated_by}
            for d in drafts
        ],
        "runs": [
            {"id": r.id, "status": r.status, "created_at": r.created_at.isoformat()} for r in runs
        ],
        "semantic": semantic,
    }


async def save_research_results(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist normalized papers for one project. Dedupe is enforced in the DB."""
    req = SaveResultsInput.model_validate(payload)
    saved = 0
    skipped = 0
    async with SessionLocal() as session:
        project = await session.get(Project, req.project_id)
        if project is None:
            return {"tool": "save_research_results", "ok": False, "error": "project not found"}
        existing = (
            await session.execute(
                select(Paper.dedupe_key).where(Paper.project_id == req.project_id)
            )
        ).scalars().all()
        seen = set(existing)
        for p in req.papers:
            key = (
                f"doi:{p.doi}"
                if p.doi
                else (f"arxiv:{p.arxiv_id}" if p.arxiv_id else f"title:{normalize_title(p.title)}")
            )
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            session.add(
                Paper(
                    project_id=req.project_id,
                    run_id=req.run_id,
                    dedupe_key=key[:280],
                    doi=p.doi,
                    arxiv_id=p.arxiv_id,
                    title=p.title,
                    norm_title=normalize_title(p.title),
                    authors_json=p.authors,
                    year=p.year,
                    venue=p.venue,
                    abstract=p.abstract,
                    url=p.url,
                    pdf_url=p.pdf_url,
                    cited_by=p.cited_by,
                    type=p.type,
                    sources_json=p.sources or [p.source],
                    source_queries_json={},
                )
            )
            saved += 1
        await session.commit()

        # Keep the semantic index in step with stored records (Lab 4).
        index_note = None
        if saved:
            try:
                from app.services.embeddings import index_papers

                project_papers = (
                    await session.execute(select(Paper).where(Paper.project_id == req.project_id))
                ).scalars().all()
                info = await index_papers(session, req.project_id, project_papers)
                await session.commit()
                index_note = info
            except Exception as exc:  # noqa: BLE001
                index_note = {"error": f"{exc.__class__.__name__}: {exc}"}
    return {
        "index": index_note,
        "tool": "save_research_results",
        "ok": True,
        "saved": saved,
        "skipped_duplicates": skipped,
        "project_id": req.project_id,
    }


async def generate_research_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Compose a Markdown report from stored project data and write it to disk."""
    req = ReportInput.model_validate(payload)
    async with SessionLocal() as session:
        project = await session.get(Project, req.project_id)
        if project is None:
            return {"tool": "generate_research_report", "ok": False, "error": "project not found"}
        papers = (
            await session.execute(
                select(Paper)
                .where(Paper.project_id == req.project_id)
                .order_by(Paper.rank_score.desc())
                .limit(50)
            )
        ).scalars().all()
        gaps = (
            await session.execute(
                select(ResearchGap).where(ResearchGap.project_id == req.project_id)
            )
        ).scalars().all()
        draft = None
        if req.include_draft:
            draft = (
                await session.execute(
                    select(Draft)
                    .where(Draft.project_id == req.project_id)
                    .order_by(Draft.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

    lines = [
        f"# Research Report — {project.name}",
        "",
        f"**Topic:** {project.topic}",
        f"**Project ID:** `{project.id}`",
        f"**Generated:** {_now()}",
        "",
        f"## Literature ({len(papers)} records)",
        "",
    ]
    for i, p in enumerate(papers, 1):
        cite = p.doi or (f"arXiv:{p.arxiv_id}" if p.arxiv_id else p.url or "no identifier")
        lines.append(f"{i}. **{p.title}** ({p.year or 'n.d.'}) — {cite}")
        if p.url:
            lines.append(f"   <{p.url}>")
    lines += ["", f"## Research gaps ({len(gaps)})", ""]
    for g in gaps:
        lines.append(f"### {g.title}")
        lines.append(f"*Type:* {g.kind} · *confidence:* {g.confidence:.2f}")
        lines.append("")
        lines.append(g.description)
        if g.rationale:
            lines.append(f"\n**Why:** {g.rationale}")
        lines.append("")
    if draft:
        lines += ["", f"## Draft (v{draft.version}, {draft.status})", "", draft.markdown]

    content = "\n".join(lines)
    export_dir = settings.export_path / _safe_dir(project.id)
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"research_report_{time.strftime('%Y%m%d_%H%M%S')}.md"
    path.write_text(content, encoding="utf-8")
    return {
        "tool": "generate_research_report",
        "ok": True,
        "filename": path.name,
        "rel_path": str(path.relative_to(settings.export_path)),
        "bytes": len(content.encode("utf-8")),
        "papers": len(papers),
        "gaps": len(gaps),
        "generated_at": _now(),
    }


def _safe_dir(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_") or "project"


async def read_research_file(payload: dict[str, Any]) -> dict[str, Any]:
    """Read a file, but only inside DATA_DIR or EXPORT_DIR (Lab 12 safe file access)."""
    req = ReadFileInput.model_validate(payload)
    raw = req.rel_path.strip()
    if raw.startswith("/") or ".." in Path(raw).parts or raw.startswith("~"):
        return {
            "tool": "read_research_file",
            "ok": False,
            "error": "path rejected: only relative paths inside data/ or exports/ are allowed",
        }
    for root in (settings.data_path, settings.export_path):
        candidate = (root / raw).resolve()
        if not str(candidate).startswith(str(root.resolve())):
            continue
        if candidate.is_file():
            data = candidate.read_bytes()[: req.max_bytes]
            return {
                "tool": "read_research_file",
                "ok": True,
                "path": raw,
                "bytes": len(data),
                "truncated": candidate.stat().st_size > req.max_bytes,
                "content": data.decode("utf-8", errors="replace"),
            }
    return {"tool": "read_research_file", "ok": False, "error": f"file not found under allowed roots: {raw}"}





def summarise_result(name: str, result: dict[str, Any]) -> str:
    """Short human-readable summary stored with each tool invocation."""
    if not isinstance(result, dict):
        return f"non-dict result: {type(result).__name__}"
    for key in ("count", "saved", "unique_count", "candidates"):
        if key in result:
            return f"{name}: {key}={result[key]} status={result.get('status','ok')}"
    if "filename" in result:
        return f"{name}: wrote {result['filename']} ({result.get('bytes', 0)} bytes)"
    if "paper_count" in result:
        return f"{name}: wires {result['paper_count']} stored papers"
    return json.dumps(result, default=str)[:200]


# ---------------------------------------------------------------------------
# Domain-radar tools: funding, venues, collaborators (real sources only)
# ---------------------------------------------------------------------------
async def find_topic_funders(payload: dict[str, Any]) -> dict[str, Any]:
    """Funders visible in the literature for a topic — evidence, not grant calls.

    Sources: OpenAlex `funders` entities (matched by topic keywords) and the
    funder/award metadata attached to real works on the topic. Nothing here
    invents deadlines, amounts or eligibility.
    """
    from app.tools.specs import FunderInput

    req = FunderInput.model_validate(payload)
    works, fetch_works = await openalex.works_with_funders(req.query, limit=min(req.limit * 5, 50))
    entities, fetch_funders = await openalex.funders_search(req.query, limit=req.limit)

    per_funder: dict[str, dict[str, Any]] = {}
    for w in works:
        for f in w.get("funders") or []:
            name = f.get("display_name")
            if not name:
                continue
            entry = per_funder.setdefault(
                name,
                {
                    "funder": name,
                    "openalex_id": f.get("id"),
                    "ror": f.get("ror"),
                    "award_ids": [],
                    "papers": [],
                },
            )
            for a in w.get("awards") or []:
                if a.get("funder_display_name") == name and a.get("funder_award_id"):
                    if a["funder_award_id"] not in entry["award_ids"]:
                        entry["award_ids"].append(a["funder_award_id"])
            if len(entry["papers"]) < 5:
                entry["papers"].append(
                    {"title": (w.get("title") or "")[:160], "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
                     "year": w.get("publication_year"), "url": w.get("id")}
                )

    evidence_funders = sorted(per_funder.values(), key=lambda e: -len(e["papers"]))
    directory = []
    for f in entities[: req.limit]:
        directory.append(
            {
                "name": f.get("display_name"),
                "openalex_id": f.get("id"),
                "country_code": f.get("country_code"),
                "homepage_url": f.get("homepage_url"),
                "awards_count": f.get("awards_count"),
                "works_count": f.get("works_count"),
                "source_url": f.get("id"),
            }
        )
    return {
        "tool": "find_topic_funders",
        "query": req.query,
        "status": fetch_works.status,
        "error": fetch_works.error or fetch_funders.error,
        "retrieved_at": _now(),
        "funders_in_literature": evidence_funders[: req.limit],
        "funder_directory_matches": directory,
        "coverage": {
            "works_scanned": len(works),
            "works_with_funder_metadata": sum(1 for w in works if w.get("funders")),
        },
        "disclaimer": (
            "These are funders and award numbers recorded on real publications, plus OpenAlex "
            "funder entities matching the topic. This is NOT a list of open calls: deadlines, "
            "amounts and eligibility are not available from these sources and are never guessed."
        ),
    }


async def verify_venue(payload: dict[str, Any]) -> dict[str, Any]:
    """Verify a venue name against Crossref's journal registry (ISSN + publisher)."""
    from app.tools.specs import VenueInput

    req = VenueInput.model_validate(payload)
    items, fetch = await crossref.journal_search(req.name, limit=max(req.limit, 3))
    matches = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        sim = _title_similarity(req.name, title)
        matches.append(
            {
                "title": title,
                "publisher": it.get("publisher"),
                "issn": (it.get("ISSN") or [None])[0],
                "issn_all": it.get("ISSN") or [],
                "doi_count_current": (it.get("counts") or {}).get("current-dois"),
                "doi_count_total": (it.get("counts") or {}).get("total-dois"),
                "similarity": round(sim, 3),
                # Only a near-exact title match counts as verified. Crossref's journal
                # search is fuzzy and will happily return unrelated titles for a
                # conference name, so a loose match must never be reported as proof.
                "verification": "verified" if sim >= 0.92 else "unverified",
                "source_url": f"https://api.crossref.org/journals/{(it.get('ISSN') or [''])[0]}",
            }
        )
    matches.sort(key=lambda m: -m["similarity"])
    return {
        "tool": "verify_venue",
        "query": req.name,
        "status": fetch.status,
        "error": fetch.error,
        "retrieved_at": _now(),
        "matches": matches,
        "best_match": matches[0] if matches else None,
        "match_note": (
            None
            if not matches
            else (
                "Near-exact title match in the Crossref journal registry."
                if matches[0]["similarity"] >= 0.92
                else f"Closest registry title matches only loosely (similarity {matches[0]['similarity']}); "
                "this venue is NOT confirmed — conference proceedings and books often have no journal record."
            )
        ),
        "disclaimer": (
            "Crossref confirms title, ISSN and publisher only. Impact factor, acceptance rate "
            "and indexing status are NOT provided by this source and are never inferred."
        ),
    }


def _title_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    from app.services.scholarly.records import normalize_title

    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


async def find_collaborators(payload: dict[str, Any]) -> dict[str, Any]:
    """Identify researchers active on a topic from real authorship records."""
    from app.tools.specs import CollaboratorInput

    req = CollaboratorInput.model_validate(payload)
    works, fetch = await openalex.works_with_funders(req.query, limit=min(req.limit * 5, 50))
    exclude = {n.lower() for n in req.exclude_authors}

    people: dict[str, dict[str, Any]] = {}
    for w in works:
        for authorship in w.get("authorships") or []:
            author = authorship.get("author") or {}
            aid = author.get("id")
            name = author.get("display_name")
            if not aid or not name or name.lower() in exclude:
                continue
            entry = people.setdefault(
                aid,
                {
                    "author_key": aid,
                    "name": name,
                    "orcid": author.get("orcid"),
                    "institutions": [],
                    "papers": [],
                    "years": [],
                },
            )
            for inst in authorship.get("institutions") or []:
                iname = inst.get("display_name")
                if iname and iname not in entry["institutions"]:
                    entry["institutions"].append(iname)
            if len(entry["papers"]) < 6:
                entry["papers"].append(
                    {
                        "title": (w.get("title") or "")[:180],
                        "year": w.get("publication_year"),
                        "doi": (w.get("doi") or "").replace("https://doi.org/", "") or None,
                        "url": w.get("id"),
                    }
                )
            if w.get("publication_year"):
                entry["years"].append(w["publication_year"])

    ranked = []
    for p in people.values():
        n = len(p["papers"])
        recent = max(p["years"]) if p["years"] else None
        interest = round(min(1.0, n / max(len(works), 1) * 2), 3)
        p["similarity"] = interest
        p["papers_in_retrieved_set"] = n
        p["latest_year"] = recent
        p["evidence_note"] = (
            f"{n} paper(s) in the retrieved set on this exact query; "
            f"topic overlap is measured by co-occurrence in those records."
        )
        p.pop("years", None)
        ranked.append(p)
    ranked.sort(key=lambda p: (-p["papers_in_retrieved_set"], -(p["latest_year"] or 0)))

    return {
        "tool": "find_collaborators",
        "query": req.query,
        "status": fetch.status,
        "error": fetch.error,
        "retrieved_at": _now(),
        "candidates": ranked[: req.limit],
        "scanned_works": len(works),
        "disclaimer": (
            "Candidates are real authors of retrieved records. Research similarity is NOT evidence "
            "that a person is available, willing or funded to collaborate, and no contact details "
            "are inferred. Verify affiliation on the linked OpenAlex profile."
        ),
    }


TOOL_IMPLS = {
    "search_openalex": search_openalex,
    "search_crossref": search_crossref,
    "search_arxiv": search_arxiv,
    "search_all_sources": search_all_sources,
    "lookup_doi": lookup_doi,
    "get_paper_details": get_paper_details,
    "compare_papers": compare_papers,
    "retrieve_project_memory": retrieve_project_memory,
    "save_research_results": save_research_results,
    "generate_research_report": generate_research_report,
    "read_research_file": read_research_file,
    "find_topic_funders": find_topic_funders,
    "verify_venue": verify_venue,
    "find_collaborators": find_collaborators,
}
