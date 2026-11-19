"""Agent 6 — Collaboration Agent.

Candidates are real authors of real retrieved records. Research similarity comes
from co-occurrence in the retrieved corpus and is labelled as such; availability,
funding and contact details are never inferred.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from app.db.base import SessionLocal
from app.db.models import Collaborator
from app.logging_conf import get_logger
from app.runtime.runtime import AgentRuntime
from app.tools.runner import ToolRunner

log = get_logger("agents.collaboration")


class CollaborationAgent:
    name = "CollaborationAgent"

    def __init__(self, runtime: AgentRuntime, tools: ToolRunner) -> None:
        self.runtime = runtime
        self.tools = tools

    async def run(
        self,
        *,
        project_id: str,
        topic: str,
        exclude_authors: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        await self.runtime.progress("collaboration", "Finding active researchers on this topic", agent=self.name)
        res = await self.tools.call(
            "find_collaborators",
            {"query": topic, "limit": limit, "exclude_authors": exclude_authors or []},
        )
        self.runtime.stats.tool_calls += 1
        candidates = res.get("candidates") or []

        await self._persist(project_id, candidates)
        await self.runtime.emit(
            "collaborators_ready",
            stage="collaboration",
            count=len(candidates),
            status=res.get("status"),
            error=res.get("error"),
        )
        warnings = []
        if res.get("status") != "ok":
            warnings.append(
                f"collaborator search degraded: status={res.get('status')} error={res.get('error')}"
            )
        if not candidates:
            warnings.append(
                "No collaborator candidates could be derived from the retrieved corpus; this is "
                "reported rather than filled with invented names."
            )
        return {
            "candidates": candidates,
            "disclaimer": res.get("disclaimer"),
            "scanned_works": res.get("scanned_works"),
            "status": res.get("status"),
            "warnings": warnings,
        }

    async def _persist(self, project_id: str, candidates: list[dict[str, Any]]) -> None:
        async with SessionLocal() as session:
            await session.execute(
                delete(Collaborator).where(
                    Collaborator.project_id == project_id, Collaborator.run_id == self.runtime.run_id
                )
            )
            for c in candidates:
                session.add(
                    Collaborator(
                        project_id=project_id,
                        run_id=self.runtime.run_id,
                        name=c.get("name", "unknown"),
                        author_key=(c.get("author_key") or "")[:255] or None,
                        works_count=c.get("papers_in_retrieved_set", 0),
                        relevant_papers=c.get("papers", []),
                        similarity=float(c.get("similarity", 0.0)),
                        evidence_note=c.get("evidence_note", ""),
                        source_url=c.get("author_key"),
                    )
                )
            await session.commit()
