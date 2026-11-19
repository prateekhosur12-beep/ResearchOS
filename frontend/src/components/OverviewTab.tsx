import React, { useEffect, useMemo, useState } from "react";
import type { TabProps } from "../App";
import type { RunDetail } from "../types";
import { isLive, type RunEvent } from "../useRun";
import { StageTimeline } from "./StageTimeline";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  CheckLine,
  Divider,
  Dot,
  ErrorNote,
  Field,
  Note,
  Select,
  StatusPill,
  Toggle,
  fmtDuration,
  fmtTime,
  relTime,
} from "./ui";
import {
  IconBranch,
  IconChevronRight,
  IconDoc,
  IconPlay,
  IconQuote,
  IconSpinner,
  IconStop,
} from "./icons";

const DEFAULT_CONFIG = {
  result_limit: 20,
  min_papers: 8,
  generate_draft: true,
  run_radar: true,
  run_collaboration: true,
  max_attempts: 2,
};

export function OverviewTab({
  projectId,
  detail,
  refreshKey,
  onReload,
  goTo,
  run,
  events,
  onStart,
  onCancel,
  starting,
  cancelling,
  runError,
}: TabProps & {
  run: RunDetail | null;
  events: RunEvent[];
  onStart: (config: Record<string, unknown>) => Promise<void>;
  onCancel: (reason?: string) => Promise<void>;
  starting: boolean;
  cancelling: boolean;
  runError: string | null;
}) {
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG });
  const [showConfig, setShowConfig] = useState(false);

  // a run that was already going when the page loaded should show its config
  useEffect(() => {
    if (run?.config) {
      setConfig((prev) => ({ ...prev, ...pickConfig(run.config) }));
    }
  }, [run?.id]);

  const plan = detail?.query_plan;
  const live = isLive(run?.status);
  const stats = (run?.stats ?? {}) as Record<string, any>;
  // Project total (all runs) is what the card claims; the run's own retrieval is the hint.
  const papers: number = detail?.paper_count ?? stats.papers ?? 0;
  const runPapers: number | null = stats.papers ?? null;
  // per_source rows of the last discovery attempt — the real per-source results
  const sourceReports: any[] = stats.discovery?.per_source ?? [];
  // Prefer the stored artifact on the project: the latest run may be a cancelled one
  // that produced nothing, and the overview must not then look empty.
  const citationSummary = stats.citation_summary ?? detail?.citation_summary ?? null;
  const coverage = stats.gap_coverage ?? null;
  const warnings: string[] = useMemo(() => {
    const list: string[] = [...(stats.warnings ?? [])];
    for (const s of sourceReports) {
      if (s.status !== "ok" && s.status !== "available") {
        list.push(`${s.source}: ${s.status}${s.error ? ` (${s.error})` : ""}`);
      }
    }
    if (run?.status === "failed" && run.error) list.push(`run failed: ${run.error}`);
    if (run?.status === "cancelled")
      list.push(`run cancelled: ${stats.cancel_reason ?? "no reason recorded"}`);
    return Array.from(new Set(list));
  }, [sourceReports, run, stats]);

  const stageEvents = events.filter((e) => e.type === "stage").slice(-3).reverse();

  return (
    <div className="space-y-4">
      {/* summary cards — real counts from the database */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <button className="text-left" onClick={() => goTo("literature")}>
          <div className="card px-4 py-3 transition-colors hover:border-slate-300">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium uppercase tracking-wide text-ink-400">Papers</span>
              <IconDoc size={14} className="text-ink-300" />
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-[22px] font-semibold leading-tight text-ink-900">{papers}</span>
              <span className="text-2xs text-ink-400">
                {sourceReports.length
                  ? `${new Set(sourceReports.filter((s: any) => s.status === "ok").map((s: any) => s.source)).size}/3 sources ok${
                      runPapers !== null ? ` · ${runPapers} this run` : ""
                    }`
                  : "stored in this project"}
              </span>
            </div>
          </div>
        </button>

        <button className="text-left" onClick={() => goTo("gaps")}>
          <div className="card px-4 py-3 transition-colors hover:border-slate-300">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium uppercase tracking-wide text-ink-400">Gaps / ideas</span>
              <IconBranch size={14} className="text-ink-300" />
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-[22px] font-semibold leading-tight text-ink-900">
                {detail?.gap_count ?? 0}
                <span className="text-ink-300"> / </span>
                {detail?.idea_count ?? 0}
              </span>
              <span className="text-2xs text-ink-400">evidence-linked</span>
            </div>
          </div>
        </button>

        <button className="text-left" onClick={() => goTo("draft")}>
          <div className="card px-4 py-3 transition-colors hover:border-slate-300">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium uppercase tracking-wide text-ink-400">Draft</span>
              <IconDoc size={14} className="text-ink-300" />
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-[22px] font-semibold leading-tight text-ink-900">
                {detail?.draft_version ? `v${detail.draft_version}` : "—"}
              </span>
              <span className="text-2xs text-ink-400">
                {detail?.draft_word_count
                  ? `${detail.draft_word_count} words · ${detail.draft_status ?? "draft"}`
                  : "not generated"}
              </span>
            </div>
          </div>
        </button>

        <button className="text-left" onClick={() => goTo("citations")}>
          <div className="card px-4 py-3 transition-colors hover:border-slate-300">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium uppercase tracking-wide text-ink-400">Citations</span>
              <IconQuote size={14} className="text-ink-300" />
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-[22px] font-semibold leading-tight text-ink-900">
                {citationSummary ? `${citationSummary.doi_verified ?? 0}/${citationSummary.references ?? 0}` : "—"}
              </span>
              <span className="text-2xs text-ink-400">
                {citationSummary ? "DOIs verified live" : "no audit yet"}
              </span>
            </div>
          </div>
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* ------------------------------------------------------- run panel */}
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Research run"
              description="Twelve stages, executed by the backend. Nothing here is simulated."
              actions={
                <>
                  <Button variant="ghost" size="sm" onClick={() => setShowConfig((v) => !v)}>
                    {showConfig ? "Hide settings" : "Settings"}
                  </Button>
                  {live ? (
                    <Button
                      variant="danger"
                      size="sm"
                      icon={cancelling ? <IconSpinner size={13} /> : <IconStop size={13} />}
                      onClick={() => onCancel("Cancelled from the UI")}
                      disabled={cancelling}
                    >
                      {cancelling ? "Cancelling…" : "Cancel run"}
                    </Button>
                  ) : (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={starting ? <IconSpinner size={13} /> : <IconPlay size={13} />}
                      onClick={() => onStart(config)}
                      disabled={starting || !projectId}
                    >
                      {starting ? "Starting…" : "Run research"}
                    </Button>
                  )}
                </>
              }
            />

            {showConfig && (
              <div className="mb-3 rounded-md border border-slate-200 bg-slate-50/70 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Results per source" hint="OpenAlex / Crossref / arXiv page size">
                    <Select
                      value={config.result_limit}
                      onChange={(e) => setConfig({ ...config, result_limit: Number(e.target.value) })}
                      disabled={live}
                    >
                      {[10, 15, 20, 30, 40].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Minimum papers" hint="Below this the run reports partial evidence">
                    <Select
                      value={config.min_papers}
                      onChange={(e) => setConfig({ ...config, min_papers: Number(e.target.value) })}
                      disabled={live}
                    >
                      {[3, 5, 8, 12, 20].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-4">
                  <Toggle
                    label="Generate draft"
                    hint="Manuscript v1 + bibliography"
                    checked={config.generate_draft}
                    disabled={live}
                    onChange={(v) => setConfig({ ...config, generate_draft: v })}
                  />
                  <Toggle
                    label="Venue & funding scan"
                    hint="Radar stage (Crossref / OpenAlex)"
                    checked={config.run_radar}
                    disabled={live}
                    onChange={(v) => setConfig({ ...config, run_radar: v })}
                  />
                  <Toggle
                    label="Collaborator scan"
                    hint="Based on corpus overlap only"
                    checked={config.run_collaboration}
                    disabled={live}
                    onChange={(v) => setConfig({ ...config, run_collaboration: v })}
                  />
                  <Toggle
                    label="Two search attempts"
                    hint="Retry with tightened queries when thin"
                    checked={config.max_attempts > 1}
                    disabled={live}
                    onChange={(v) => setConfig({ ...config, max_attempts: v ? 2 : 1 })}
                  />
                </div>
              </div>
            )}

            {runError && (
              <div className="mb-3">
                <ErrorNote title="Run controller">{runError}</ErrorNote>
              </div>
            )}

            {run ? (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[12.5px] text-ink-500">
                  <span className="flex items-center gap-1.5">
                    <StatusPill status={run.status} />
                    <span className="text-2xs text-ink-400">{run.id.slice(0, 8)}</span>
                  </span>
                  <span>started {relTime(run.created_at)}</span>
                  {run.finished_at && <span>finished {fmtTime(run.finished_at)}</span>}
                  {run.status !== "pending" && (
                    <span>
                      elapsed {fmtDuration(
                        new Date(run.finished_at ?? Date.now()).getTime() - new Date(run.created_at).getTime(),
                      )}
                    </span>
                  )}
                  {run.config?.result_limit && <span>limit {run.config.result_limit}</span>}
                </div>

                {run.status === "cancelled" && (
                  <div className="mb-3">
                    <Note tone="warn">
                      <strong>Cancelled</strong> — {String(stats.cancel_reason ?? "reason not recorded")}
                      {Array.isArray(stats.pending_artifacts) && stats.pending_artifacts.length > 0 && (
                        <> · not produced: {stats.pending_artifacts.join(", ")}</>
                      )}
                    </Note>
                  </div>
                )}
                {run.status === "failed" && run.error && (
                  <div className="mb-3">
                    <ErrorNote title="Run failed">{run.error}</ErrorNote>
                  </div>
                )}

                <StageTimeline stages={run.stages ?? []} />

                {live && stageEvents.length > 0 && (
                  <p className="mt-2 flex items-center gap-1.5 text-2xs text-ink-400">
                    <Dot tone="info" pulse /> live: {stageEvents[0].stage}{" "}
                    {stageEvents[0].status ? `→ ${stageEvents[0].status}` : ""}
                  </p>
                )}

                {(run.status === "awaiting_approval" || run.status === "completed") && (
                  <div className="mt-3 flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                    <span className="text-[13px] text-ink-600">
                      Run finished with {run.stages?.filter((s) => s.status === "completed").length ?? 0}/12 stages
                      completed. Review the artifacts, then approve or reject.
                    </span>
                    <Button variant="secondary" size="sm" onClick={() => goTo("draft")}>
                      Review draft <IconChevronRight size={13} />
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <Note>
                No run yet for this project. Press <strong>Run research</strong> to execute the twelve-stage workflow
                against the live scholarly APIs.
              </Note>
            )}
          </Card>

          {/* source results of the last run */}
          {sourceReports.length > 0 && (
            <Card>
              <CardHeader
                title="What the swarm actually returned"
                description={`Last run · ${stats.queries?.length ?? 0} queries × 3 sources dispatched`}
                actions={
                  <Button variant="ghost" size="sm" onClick={() => goTo("trace")}>
                    Full trace
                  </Button>
                }
              />
              <table className="table-base">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th className="text-right">Records</th>
                    <th className="text-right">Latency</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {sourceReports.map((s: any, i: number) => (
                    <tr key={`${s.source}-${i}`}>
                      <td className="font-medium text-ink-800">{s.source}</td>
                      <td>
                        <StatusPill status={s.status} />
                      </td>
                      <td className="text-right tabular-nums">{s.records ?? s.count ?? "—"}</td>
                      <td className="text-right tabular-nums">{fmtDuration(s.latency_ms)}</td>
                      <td className="max-w-[280px] truncate text-2xs text-ink-500" title={s.error ?? s.detail}>
                        {s.error ?? s.detail ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {coverage && (
            <Card>
              <CardHeader
                title="Evidence coverage"
                description="How much of the corpus could actually support an evidence-based claim."
              />
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <CoverageTile label="papers" value={coverage.papers} />
                <CoverageTile
                  label="with abstract"
                  value={`${Math.round((coverage.abstract_coverage ?? 0) * 100)}%`}
                  hint={`${coverage.with_abstract ?? 0} of ${coverage.papers}`}
                />
                <CoverageTile
                  label="state limitations"
                  value={`${Math.round((coverage.limitation_coverage ?? 0) * 100)}%`}
                  hint={`${coverage.with_stated_limitations ?? 0} papers`}
                  tone={(coverage.limitation_coverage ?? 0) < 0.15 ? "warn" : "neutral"}
                />
                <CoverageTile
                  label="method signals"
                  value={Object.keys(coverage.method_frequency ?? {}).length}
                  hint="distinct families detected"
                />
              </div>
              {coverage.method_frequency && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {Object.entries(coverage.method_frequency as Record<string, number>)
                    .sort((a, b) => b[1] - a[1])
                    .map(([m, n]) => (
                      <Badge key={m} tone="neutral">
                        {m} {n}
                      </Badge>
                    ))}
                </div>
              )}
            </Card>
          )}

          {warnings.length > 0 && (
            <Card>
              <CardHeader title="Honest warnings" description="Things that did not go cleanly in this run." />
              <ul className="space-y-1 text-[13px] text-warn-700">
                {warnings.map((w) => (
                  <li key={w} className="flex items-start gap-2">
                    <span className="mt-1.5"><Dot tone="warn" /></span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* --------------------------------------------------- right column */}
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Search plan"
              description={`Generated by ${plan?.generated_by ?? "rules"} · max ${plan?.max_query_chars ?? 400} chars`}
              actions={
                <Button variant="ghost" size="sm" onClick={onReload} title="Recompute">
                  Reload
                </Button>
              }
            />
            {plan ? (
              <>
                <ol className="space-y-1.5">
                  {plan.queries.map((q: string, i: number) => (
                    <li key={i} className="flex items-start gap-2 text-[12.5px]">
                      <span className="mt-0.5 w-4 shrink-0 text-right text-2xs tabular-nums text-ink-300">{i + 1}</span>
                      <span className="min-w-0 flex-1 break-words rounded bg-slate-50 px-2 py-1 font-mono text-[11.5px] text-ink-700">
                        {q}
                      </span>
                      <span
                        className={`shrink-0 text-2xs tabular-nums ${
                          q.length > 380 ? "text-warn-700" : "text-ink-300"
                        }`}
                      >
                        {q.length}
                      </span>
                    </li>
                  ))}
                </ol>
                <Divider />
                <div className="space-y-1.5">
                  <CheckLine ok={plan.queries.every((q: string) => q.length <= (plan.max_query_chars ?? 400))}>
                    every query under {(plan.max_query_chars ?? 400)} characters
                  </CheckLine>
                  <CheckLine ok={!plan.queries.some((q: string) => q === detail?.topic && q.length > 120)}>
                    no raw brief forwarded as a query
                  </CheckLine>
                  <CheckLine ok={new Set(plan.queries).size === plan.queries.length}>queries de-duplicated</CheckLine>
                  <CheckLine ok={plan.used_instructions ? false : true}>
                    {plan.used_instructions
                      ? "brief keywords were folded into query text"
                      : "brief kept as context only (not dispatched)"}
                  </CheckLine>
                </div>
                {plan.warnings?.length > 0 && (
                  <ul className="mt-2 space-y-1 text-2xs text-warn-700">
                    {plan.warnings.map((w: string) => (
                      <li key={w}>· {w}</li>
                    ))}
                  </ul>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {plan.keywords?.slice(0, 8).map((k: string) => (
                    <Badge key={k} tone="neutral">
                      {k}
                    </Badge>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-[13px] text-ink-400">Plan preview unavailable.</p>
            )}
          </Card>

          <Card>
            <CardHeader title="Brief given to the agents" description="Context only — never sent to search APIs." />
            <p className="whitespace-pre-wrap text-[12.5px] leading-6 text-ink-600">
              {detail?.research_instructions || <span className="text-ink-400">No instructions provided.</span>}
            </p>
            {detail?.research_questions?.length ? (
              <>
                <Divider />
                <p className="section-title mb-1">Questions</p>
                <ol className="list-decimal space-y-1 pl-4 text-[12.5px] text-ink-600">
                  {detail.research_questions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ol>
              </>
            ) : null}
            <Divider />
            <div className="grid grid-cols-2 gap-y-1 text-2xs text-ink-400">
              <span>created</span>
              <span className="text-right text-ink-600">{fmtTime(detail?.created_at)}</span>
              <span>runs</span>
              <span className="text-right text-ink-600">{detail?.run_count ?? 0}</span>
              <span>domain</span>
              <span className="text-right text-ink-600">{detail?.domain?.replace(/_/g, " ")}</span>
            </div>
          </Card>

          {run && (
            <Card>
              <CardHeader title="Run history" description={`${detail?.runs?.length ?? 0} run(s) for this project`} />
              <ul className="space-y-1.5">
                {(detail?.runs ?? []).slice(0, 6).map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2 text-[12.5px]">
                    <span className="flex items-center gap-1.5">
                      <StatusPill status={r.status} />
                      <span className="text-2xs text-ink-400">{r.id.slice(0, 6)}</span>
                    </span>
                    <span className="text-2xs text-ink-400">{relTime(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function CoverageTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "neutral" | "warn";
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 px-2.5 py-1.5">
      <p className="text-2xs uppercase tracking-wide text-ink-400">{label}</p>
      <p className={`text-[16px] font-semibold tabular-nums ${tone === "warn" ? "text-warn-700" : "text-ink-900"}`}>
        {value}
      </p>
      {hint && <p className="text-2xs text-ink-400">{hint}</p>}
    </div>
  );
}

function pickConfig(cfg: Record<string, any>) {
  return {
    result_limit: cfg.result_limit ?? DEFAULT_CONFIG.result_limit,
    min_papers: cfg.min_papers ?? DEFAULT_CONFIG.min_papers,
    generate_draft: cfg.generate_draft ?? DEFAULT_CONFIG.generate_draft,
    run_radar: cfg.run_radar ?? DEFAULT_CONFIG.run_radar,
    run_collaboration: cfg.run_collaboration ?? DEFAULT_CONFIG.run_collaboration,
    max_attempts: cfg.max_attempts ?? DEFAULT_CONFIG.max_attempts,
  };
}
