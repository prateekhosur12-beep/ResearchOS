import React, { useState } from "react";
import { api } from "../api";
import type { TabProps } from "../App";
import type { Gap, Idea } from "../types";
import { useAsync } from "../hooks";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorNote,
  Note,
  Spinner,
  Toggle,
} from "./ui";
import { IconBranch, IconExternal, IconSearch } from "./icons";

export function GapsTab({ projectId, refreshKey, goTo }: TabProps) {
  const [showIdeas, setShowIdeas] = useState(true);
  const gaps = useAsync(() => api.gaps(projectId), [projectId, refreshKey]);
  const ideas = useAsync(() => api.ideas(projectId), [projectId, refreshKey]);

  const gapList: Gap[] = gaps.data?.gaps ?? [];
  const ideaList: Idea[] = ideas.data?.ideas ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold text-ink-900">Gaps and research ideas</h2>
          <p className="mt-0.5 text-[13px] text-ink-500">
            Every gap must cite papers already in this project's corpus. Ideas are proposals — nothing here has been
            executed.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => { gaps.reload(); ideas.reload(); }}>
          Refresh
        </Button>
      </div>

      {gaps.error && <ErrorNote>{gaps.error}</ErrorNote>}
      {gaps.loading && !gaps.data && <Spinner label="Loading gaps…" />}

      {!gaps.loading && gapList.length === 0 && (
        <EmptyState
          icon={<IconBranch size={22} />}
          title="No gaps recorded"
          description="Gaps are derived only from retrieved papers. If the corpus is empty or too thin, the gap agent reports that instead of inventing gaps."
          action={
            <Button variant="primary" size="sm" onClick={() => goTo("overview")}>
              Run the workflow
            </Button>
          }
        />
      )}

      <div className="space-y-3">
        {gapList.map((g, idx) => (
          <GapCard key={g.id} gap={g} index={idx + 1} />
        ))}
      </div>

      {gapList.length > 0 && (
        <>
          <div className="flex items-center justify-between pt-2">
            <div>
              <h2 className="text-[15px] font-semibold text-ink-900">Proposed research ideas</h2>
              <p className="mt-0.5 text-[13px] text-ink-500">
                Direction proposals generated from the gaps above. Treat as plans, not results.
              </p>
            </div>
            <div className="w-[220px]">
              <Toggle checked={showIdeas} onChange={setShowIdeas} label="Show ideas" hint={`${ideaList.length} proposal(s)`} />
            </div>
          </div>

          {ideas.error && <ErrorNote>{ideas.error}</ErrorNote>}
          {ideas.loading && !ideas.data && <Spinner label="Loading ideas…" />}

          {showIdeas && (
            <div className="grid gap-3 lg:grid-cols-2">
              {ideaList.map((idea, idx) => (
                <IdeaCard key={idea.id} idea={idea} index={idx + 1} />
              ))}
              {!ideas.loading && ideaList.length === 0 && (
                <Card className="lg:col-span-2">
                  <Note>No ideas were generated for this project yet.</Note>
                </Card>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function GapCard({ gap, index }: { gap: Gap; index: number }) {
  const [open, setOpen] = useState(false);
  const confidence = Math.round((gap.confidence ?? 0) * 100);
  const tone = confidence >= 70 ? "ok" : confidence >= 40 ? "warn" : "neutral";

  return (
    <Card>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-slate-100 text-2xs font-semibold text-ink-500">
          {index}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[14px] font-semibold text-ink-900">{gap.title}</h3>
            <Badge tone="neutral">{gap.kind}</Badge>
            <Badge tone={tone as any} title="Confidence computed from evidence strength">
              {confidence}% confidence
            </Badge>
            {gap.feasibility && <Badge tone="muted">feasibility: {gap.feasibility}</Badge>}
          </div>
          <p className="mt-1 text-[13.5px] leading-6 text-ink-600">{gap.description}</p>
          {gap.rationale && (
            <p className="mt-1 text-[13px] leading-6 text-ink-500">
              <span className="font-medium text-ink-600">Why it is a gap: </span>
              {gap.rationale}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            {gap.suggested_metrics?.map((m) => (
              <Badge key={m} tone="info">
                {m}
              </Badge>
            ))}
            <button
              className="text-2xs font-medium text-primary-700 hover:underline"
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Hide" : "Show"} {gap.evidence?.length ?? 0} evidence paper(s)
            </button>
          </div>

          {open && (
            <div className="mt-2 space-y-1.5 rounded-md border border-slate-200 bg-slate-50/60 p-2.5">
              {(gap.evidence ?? []).map((ev) => {
                const quote = (gap.evidence_quotes ?? []).find((q) => q.paper_id === ev.paper_id)?.quote;
                return (
                  <div key={ev.paper_id} className="text-[12.5px]">
                    <p className="font-medium text-ink-700">
                      {ev.url ? (
                        <a href={ev.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-primary-700">
                          {ev.title ?? ev.paper_id} <IconExternal size={10} />
                        </a>
                      ) : (
                        (ev.title ?? ev.paper_id)
                      )}
                      {ev.year && <span className="ml-1 text-ink-400">({ev.year})</span>}
                    </p>
                    {quote && (
                      <p className="mt-0.5 border-l-2 border-slate-300 pl-2 text-2xs italic text-ink-500">“{quote}”</p>
                    )}
                  </div>
                );
              })}
              {(gap.evidence ?? []).length === 0 && (
                <p className="text-2xs text-warn-700">No evidence papers were linked to this gap.</p>
              )}
            </div>
          )}

          <p className="mt-1.5 text-2xs text-ink-300">generated by {gap.generated_by}</p>
        </div>
      </div>
    </Card>
  );
}

function IdeaCard({ idea, index }: { idea: Idea; index: number }) {
  return (
    <Card>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary-50 text-2xs font-semibold text-primary-700">
          {index}
        </span>
        <div className="min-w-0">
          <h3 className="text-[14px] font-semibold leading-snug text-ink-900">{idea.title}</h3>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone="primary">PROPOSED</Badge>
            {idea.feasibility && <Badge tone="muted">{idea.feasibility}</Badge>}
          </div>
        </div>
      </div>

      {idea.research_questions?.length > 0 && (
        <div className="mt-2.5">
          <p className="section-title mb-1">Questions</p>
          <ul className="space-y-0.5 text-[12.5px] text-ink-600">
            {idea.research_questions.map((q, i) => (
              <li key={i} className="flex gap-1.5">
                <span className="text-ink-300">›</span>
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}

      {idea.proposed_methodology && (
        <div className="mt-2">
          <p className="section-title mb-1">Proposed method</p>
          <p className="text-[12.5px] leading-6 text-ink-600">{idea.proposed_methodology}</p>
        </div>
      )}

      <div className="mt-2 grid grid-cols-2 gap-2 text-2xs">
        {idea.suggested_datasets?.length > 0 && (
          <div>
            <p className="section-title mb-0.5">Datasets</p>
            <p className="text-ink-600">{idea.suggested_datasets.join(", ")}</p>
          </div>
        )}
        {idea.metrics?.length > 0 && (
          <div>
            <p className="section-title mb-0.5">Metrics</p>
            <p className="text-ink-600">{idea.metrics.join(", ")}</p>
          </div>
        )}
      </div>

      {idea.challenges?.length > 0 && (
        <div className="mt-2">
          <p className="section-title mb-0.5">Challenges</p>
          <ul className="space-y-0.5 text-2xs text-warn-700">
            {idea.challenges.map((c, i) => (
              <li key={i}>· {c}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-2 text-2xs text-ink-300">generated by {idea.generated_by}</p>
    </Card>
  );
}
