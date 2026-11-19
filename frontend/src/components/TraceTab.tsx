import React, { useState } from "react";
import { api } from "../api";
import type { TabProps } from "../App";
import type { RunDetail } from "../types";
import { useAsync } from "../hooks";
import { StageTimeline } from "./StageTimeline";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorNote,
  Note,
  Spinner,
  StatusPill,
  fmtDuration,
  fmtTime,
  relTime,
} from "./ui";
import { IconChevronDown, IconChevronRight, IconList } from "./icons";

const SUBTABS = ["Stages", "Agent steps", "Tool calls", "Source attempts", "Audit chain"] as const;
type Sub = (typeof SUBTABS)[number];

export function TraceTab({ projectId, refreshKey, goTo, run }: TabProps & { run: RunDetail | null }) {
  const [sub, setSub] = useState<Sub>("Stages");
  const [expanded, setExpanded] = useState<number | null>(null);

  const traceQ = useAsync(
    () => (run?.id ? api.trace(run.id) : Promise.resolve(null)),
    [run?.id, refreshKey],
  );
  const auditQ = useAsync(() => api.audit(projectId), [projectId, refreshKey]);

  const trace = traceQ.data;
  const queries: string[] = (run?.stats as any)?.queries ?? [];
  const chain = auditQ.data?.chain_verification;

  if (!run) {
    return (
      <EmptyState
        icon={<IconList size={22} />}
        title="No run to trace"
        description="Start a research run — every agent step, tool call, source attempt and query is recorded against it."
        action={
          <Button variant="primary" size="sm" onClick={() => goTo("overview")}>
            Go to run panel
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Run trace"
          description={
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-mono text-2xs">{run.id}</span>
              <span>started {relTime(run.created_at)}</span>
              {run.llm_available !== null && run.llm_available !== undefined && (
                <span>{run.llm_available ? "LLM used" : "LLM unavailable — deterministic path"}</span>
              )}
            </span>
          }
          actions={
            <>
              <StatusPill status={run.status} />
              <Button variant="ghost" size="sm" onClick={() => { traceQ.reload(); auditQ.reload(); }}>
                Refresh
              </Button>
            </>
          }
        />

        {queries.length > 0 && (
          <div className="mb-3">
            <p className="section-title mb-1">Queries dispatched ({queries.length})</p>
            <div className="space-y-1">
              {queries.map((q, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="w-4 shrink-0 text-right text-2xs tabular-nums text-ink-300">{i + 1}</span>
                  <code className="min-w-0 flex-1 break-words rounded bg-slate-50 px-2 py-0.5 text-[11.5px] text-ink-700">
                    {q}
                  </code>
                  <span className={`shrink-0 text-2xs tabular-nums ${q.length > 380 ? "text-warn-700" : "text-ink-300"}`}>
                    {q.length}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-1 border-b border-slate-100 pb-1">
          {SUBTABS.map((s) => (
            <button
              key={s}
              onClick={() => setSub(s)}
              className={`rounded-md px-2.5 py-1 text-[12.5px] font-medium ${
                sub === s ? "bg-slate-100 text-ink-900" : "text-ink-500 hover:bg-slate-50"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="pt-3">
          {traceQ.error && <ErrorNote title="Trace unavailable">{traceQ.error}</ErrorNote>}
          {traceQ.loading && !trace && <Spinner label="Loading trace…" />}

          {sub === "Stages" && <StageTimeline stages={run.stages ?? []} />}

          {sub === "Agent steps" && trace && (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th className="w-10">#</th>
                    <th className="w-36">Agent</th>
                    <th>Step</th>
                    <th className="w-20">Status</th>
                    <th className="w-20 text-right">Duration</th>
                    <th className="w-32">At</th>
                    <th className="w-6"></th>
                  </tr>
                </thead>
                <tbody>
                  {trace.steps.map((s) => (
                    <React.Fragment key={s.seq}>
                      <tr>
                        <td className="text-2xs tabular-nums text-ink-400">{s.seq}</td>
                        <td className="text-[12.5px] font-medium text-ink-700">{s.agent}</td>
                        <td className="text-[12.5px]">{s.step}</td>
                        <td>
                          <StatusPill status={s.status} />
                        </td>
                        <td className="text-right text-2xs tabular-nums">{fmtDuration(s.duration_ms)}</td>
                        <td className="text-2xs text-ink-400">{fmtTime(s.at)}</td>
                        <td>
                          {s.detail && Object.keys(s.detail).length > 0 && (
                            <button
                              onClick={() => setExpanded(expanded === s.seq ? null : s.seq)}
                              className="text-ink-400 hover:text-ink-700"
                            >
                              {expanded === s.seq ? <IconChevronDown size={13} /> : <IconChevronRight size={13} />}
                            </button>
                          )}
                        </td>
                      </tr>
                      {expanded === s.seq && (
                        <tr>
                          <td></td>
                          <td colSpan={6}>
                            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-2xs text-ink-600">
                              {JSON.stringify(s.detail, null, 2)}
                            </pre>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                  {trace.steps.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-6 text-center text-[13px] text-ink-400">
                        No agent steps were recorded for this run.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {sub === "Tool calls" && trace && (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>Tool</th>
                    <th className="w-24">Transport</th>
                    <th className="w-20">Status</th>
                    <th className="w-20 text-right">Latency</th>
                    <th>Summary</th>
                    <th className="w-20">At</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.tool_invocations.map((t, i) => (
                    <tr key={i}>
                      <td className="font-mono text-2xs text-ink-700">{t.tool}</td>
                      <td>
                        <Badge tone={t.transport === "mcp" ? "info" : "neutral"}>{t.transport}</Badge>
                      </td>
                      <td>
                        <StatusPill status={t.status} />
                      </td>
                      <td className="text-right text-2xs tabular-nums">{fmtDuration(t.latency_ms)}</td>
                      <td className="max-w-[320px] text-2xs text-ink-600">
                        <span className="line-clamp-2">{t.error ?? t.summary ?? "—"}</span>
                      </td>
                      <td className="text-2xs text-ink-400">{fmtTime(t.at)}</td>
                    </tr>
                  ))}
                  {trace.tool_invocations.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-[13px] text-ink-400">
                        No tool invocations recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {sub === "Source attempts" && trace && (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th className="w-12">Try</th>
                    <th className="w-24">Source</th>
                    <th>Query</th>
                    <th className="w-20">Status</th>
                    <th className="w-16 text-right">Records</th>
                    <th className="w-16 text-right">HTTP</th>
                    <th className="w-20 text-right">Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.source_attempts.map((a, i) => (
                    <tr key={i}>
                      <td className="text-2xs tabular-nums text-ink-400">{a.attempt}</td>
                      <td className="text-[12.5px] font-medium">{a.source}</td>
                      <td className="max-w-[280px] truncate font-mono text-2xs text-ink-600" title={a.query}>
                        {a.query}
                      </td>
                      <td>
                        <StatusPill status={a.status} />
                      </td>
                      <td className="text-right tabular-nums text-[12.5px]">{a.records}</td>
                      <td className="text-right text-2xs tabular-nums">{a.http_status ?? "—"}</td>
                      <td className="text-right text-2xs tabular-nums">{fmtDuration(a.latency_ms)}</td>
                    </tr>
                  ))}
                  {trace.source_attempts.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-6 text-center text-[13px] text-ink-400">
                        No source attempts recorded for this run.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {sub === "Audit chain" && (
            <div>
              {auditQ.loading && !auditQ.data && <Spinner label="Verifying chain…" />}
              {chain && (
                <div className="mb-3">
                  <Note tone={chain.valid ? "ok" : "danger"}>
                    <strong>{chain.valid ? "Chain intact" : "Chain broken"}</strong> — {chain.records ?? chain.records_checked ?? 0}{" "}
                    records verified{chain.reason ? `, first problem at seq ${chain.broken_at}: ${chain.reason}` : ""}.
                  </Note>
                </div>
              )}
              <div className="max-h-[420px] overflow-y-auto">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th className="w-10">#</th>
                      <th className="w-44">Action</th>
                      <th className="w-24">Actor</th>
                      <th className="w-32">At</th>
                      <th>Payload</th>
                      <th className="w-40">Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(auditQ.data?.records ?? []).slice(-60).map((r: any) => (
                      <tr key={r.seq}>
                        <td className="text-2xs tabular-nums text-ink-400">{r.seq}</td>
                        <td className="font-mono text-2xs text-ink-700">{r.action}</td>
                        <td className="text-2xs text-ink-500">{r.actor}</td>
                        <td className="text-2xs text-ink-400">{fmtTime(r.at)}</td>
                        <td className="max-w-[320px] truncate text-2xs text-ink-500" title={JSON.stringify(r.payload)}>
                          {JSON.stringify(r.payload)}
                        </td>
                        <td className="font-mono text-2xs text-ink-300">{r.hash}…</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {auditQ.data?.note && <p className="mt-2 text-2xs text-ink-400">{auditQ.data.note}</p>}
            </div>
          )}
        </div>
      </Card>

      {run.status === "cancelled" && (
        <Note tone="warn">
          This run was cancelled. Everything above is what happened up to the cancellation — no later stage ran, and no
          artifact was produced for stages that came after.
        </Note>
      )}
    </div>
  );
}
