"""Embeddings + semantic retrieval (Lab 4).

Two providers, chosen automatically and always reported to the caller:

1. `ollama:<embed_model>` — a real neural embedding model served by Ollama
   (e.g. nomic-embed-text). Chat models do NOT produce vectors, so this is a
   separate model and a separate endpoint (`/api/embed`).
2. `lexical-hash-v1` — a deterministic offline fallback: 256-dim signed feature
   hashing over unigrams+bigrams with sublinear term weighting and L2 norm.
   It is a lexical similarity measure, NOT a semantic one, and the UI says so.

Retrieval is exact cosine search over the project's stored vectors. That is
correct and O(n) at this project scale; an ANN index is unnecessary.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Paper, PaperVector
from app.logging_conf import get_logger
from app.services.llm import get_llm
from app.services.scholarly.ranking import tokenize

log = get_logger("embeddings")

LOCAL_DIM = 256
LOCAL_MODEL = "lexical-hash-v1"


def local_embed(text: str, dim: int = LOCAL_DIM) -> list[float]:
    toks = tokenize(text)
    if not toks:
        return [0.0] * dim
    feats: Counter[str] = Counter(toks)
    for a, b in zip(toks, toks[1:]):
        feats[f"{a}_{b}"] += 1
    vec = [0.0] * dim
    for feat, count in feats.items():
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        idx = h % dim
        sign = 1.0 if (h >> 63) & 1 else -1.0
        vec[idx] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))


async def embed_texts(texts: list[str]) -> tuple[list[list[float]], str, str]:
    """Return (vectors, model_label, note)."""
    if not texts:
        return [], LOCAL_MODEL, "no input"
    llm = get_llm()
    vectors = await llm.embed(texts)
    if vectors:
        return vectors, f"ollama:{llm_model_name()}", "neural embeddings from Ollama"
    return (
        [local_embed(t) for t in texts],
        LOCAL_MODEL,
        "Ollama embedding model unavailable — using deterministic lexical hashing "
        "(similarity is lexical, not semantic)",
    )


def llm_model_name() -> str:
    from app.config import settings

    return settings.ollama_embed_model


async def index_papers(session: AsyncSession, project_id: str, papers: list[Paper]) -> dict:
    if not papers:
        return {"indexed": 0, "model": LOCAL_MODEL, "note": "nothing to index"}
    texts = [
        f"{p.title}. {p.abstract or ''} {p.venue or ''} {' '.join(a.get('name','') for a in (p.authors_json or [])[:6])}"
        for p in papers
    ]
    vectors, model, note = await embed_texts(texts)

    existing = (
        await session.execute(
            select(PaperVector).where(PaperVector.project_id == project_id)
        )
    ).scalars().all()
    by_paper = {v.paper_id: v for v in existing}

    for paper, vec in zip(papers, vectors):
        row = by_paper.get(paper.id)
        if row is None:
            row = PaperVector(
                project_id=project_id,
                paper_id=paper.id,
                model=model,
                dim=len(vec),
                vector_json=vec,
            )
            session.add(row)
        else:
            row.model, row.dim, row.vector_json = model, len(vec), vec
    await session.flush()
    return {"indexed": len(papers), "model": model, "note": note}


async def semantic_search(
    session: AsyncSession,
    project_id: str,
    query: str,
    limit: int = 10,
    paper_ids: list[str] | None = None,
) -> dict:
    """Cosine search restricted to one project (no cross-project leakage)."""
    qvecs, model, note = await embed_texts([query])
    qvec = qvecs[0]
    stmt = select(PaperVector).where(PaperVector.project_id == project_id)
    rows = (await session.execute(stmt)).scalars().all()
    if paper_ids:
        allowed = set(paper_ids)
        rows = [r for r in rows if r.paper_id in allowed]
    scored = []
    for row in rows:
        if row.dim != len(qvec):
            continue  # different embedding model/dimension -> not comparable
        scored.append((cosine(qvec, row.vector_json), row.paper_id))
    scored.sort(reverse=True)
    top = scored[:limit]

    results = []
    if top:
        papers = (
            await session.execute(
                select(Paper).where(
                    Paper.project_id == project_id, Paper.id.in_([p for _, p in top])
                )
            )
        ).scalars().all()
        by_id = {p.id: p for p in papers}
        for score, pid in top:
            paper = by_id.get(pid)
            if not paper:
                continue
            results.append(
                {
                    "paper_id": pid,
                    "title": paper.title,
                    "score": round(score, 4),
                    "year": paper.year,
                    "doi": paper.doi,
                    "url": paper.url,
                }
            )
    return {
        "query": query,
        "model": model,
        "note": note,
        "candidates": len(rows),
        "results": results,
    }
