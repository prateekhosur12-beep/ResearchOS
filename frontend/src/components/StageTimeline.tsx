import React, { useState } from "react";
import type { Stage } from "../types";
import { Dot, fmtDuration } from "./ui";
import { IconAlert, IconCheck, IconChevronRight, IconMinus, IconSpinner, IconX } from "./icons";

function icon(status: Stage["status"], size = 14) {
  switch (status) {
    case "completed":
      return <IconCheck size={size} />;
    case "running":
      return <IconSpinner size={size} />;
    case "failed":
      return <IconAlert size={size} />;
    case "cancelled":
      return <IconX size={size} />;
    case "skipped":
      return <IconMinus size={size} />;
    default:
      return <span className="block h-1.5 w-1.5 rounded-full bg-slate-300" />;
  }
}

const ring: Record<Stage["status"], string> = {
  completed: "border-emerald-200 bg-success-50 text-success-700",
  running: "border-primary-200 bg-primary-50 text-primary-700",
  failed: "border-red-200 bg-danger-50 text-danger-700",
  cancelled: "border-amber-200 bg-warn-50 text-warn-700",
  skipped: "border-slate-200 bg-slate-50 text-ink-400",
  pending: "border-slate-200 bg-white text-ink-300",
};

const label: Record<Stage["status"], string> = {
  completed: "done",
  running: "running",
  failed: "failed",
  cancelled: "cancelled",
  skipped: "skipped",
  pending: "queued",
};

/** The 12 backend stages, rendered from what actually happened — never faked. */
export function StageTimeline({
  stages,
  dense = false,
  showDetail = true,
}: {
  stages: Stage[];
  dense?: boolean;
  showDetail?: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const done = stages.filter((s) => s.status === "completed").length;
  const failed = stages.filter((s) => s.status === "failed").length;
  const progress = stages.length ? Math.round((done / stages.length) * 100) : 0;

  if (!stages.length) {
    return <p className="py-3 text-[13px] text-ink-400">No stage data recorded for this run yet.</p>;
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all ${failed ? "bg-danger-600" : "bg-primary-600"}`}
            style={{ width: `${Math.max(progress, 2)}%` }}
          />
        </div>
        <span className="shrink-0 text-2xs tabular-nums text-ink-400">
          {done}/{stages.length} stages
        </span>
      </div>

      <ol className="relative">
        {stages.map((stage, idx) => {
          const isOpen = open === stage.key;
          const hasDetail = showDetail && Object.keys(stage.detail || {}).length > 0;
          return (
            <li key={stage.key} className="relative flex gap-3 pb-1">
              {idx < stages.length - 1 && (
                <span
                  className={`absolute left-[13px] top-7 h-[calc(100%-14px)] w-px ${
                    stage.status === "completed" ? "bg-emerald-200" : "bg-slate-150 bg-slate-200"
                  }`}
                />
              )}
              <span
                className={`relative z-10 mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${ring[stage.status]}`}
              >
                {icon(stage.status)}
              </span>
              <div className={`min-w-0 flex-1 ${dense ? "py-0.5" : "py-1"}`}>
                <button
                  type="button"
                  onClick={() => hasDetail && setOpen(isOpen ? null : stage.key)}
                  className={`flex w-full items-start justify-between gap-3 text-left ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
                >
                  <div className="min-w-0">
                    <span className="flex items-center gap-1.5 text-[13.5px] font-medium text-ink-800">
                      {stage.name}
                      {hasDetail && (
                        <IconChevronRight
                          size={12}
                          className={`text-ink-300 transition-transform ${isOpen ? "rotate-90" : ""}`}
                        />
                      )}
                    </span>
                    {!dense && <span className="block text-2xs text-ink-400">{stage.description}</span>}
                  </div>
                  <div className="flex shrink-0 items-center gap-2 pt-0.5 text-2xs tabular-nums text-ink-400">
                    {stage.attempts > 1 && (
                      <span className="rounded bg-amber-50 px-1 text-warn-700">{stage.attempts}×</span>
                    )}
                    {stage.tool_calls > 0 && (
                      <span title="tool calls">
                        {stage.tool_calls} {stage.tool_calls === 1 ? "tool" : "tools"}
                      </span>
                    )}
                    {stage.llm_calls > 0 && (
                      <span title="LLM calls">
                        {stage.llm_calls} {stage.llm_calls === 1 ? "llm" : "llms"}
                      </span>
                    )}
                    <span className={stage.status === "running" ? "text-primary-600" : ""}>
                      {stage.status === "running" ? "…" : fmtDuration(stage.duration_ms)}
                    </span>
                    <span className="w-14 text-right text-ink-300">{label[stage.status]}</span>
                  </div>
                </button>

                {isOpen && hasDetail && (
                  <pre className="mt-1.5 max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-md border border-slate-100 bg-slate-50 p-2 text-2xs leading-5 text-ink-600">
                    {JSON.stringify(stage.detail, null, 2)}
                  </pre>
                )}
                {stage.error && (
                  <p
                    className={`mt-1 rounded border px-2 py-1 text-2xs ${
                      stage.status === "cancelled"
                        ? "border-amber-100 bg-warn-50 text-warn-700"
                        : "border-red-100 bg-danger-50 text-danger-700"
                    }`}
                  >
                    {stage.error}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function StageChips({ stages }: { stages: Stage[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {stages.map((s) => (
        <span
          key={s.key}
          title={`${s.name} — ${s.status}`}
          className={`flex h-5 items-center gap-1 rounded-full border px-1.5 text-2xs ${ring[s.status]}`}
        >
          <Dot
            tone={
              s.status === "completed"
                ? "ok"
                : s.status === "running"
                  ? "info"
                  : s.status === "failed"
                    ? "danger"
                    : s.status === "cancelled"
                      ? "warn"
                      : "muted"
            }
            pulse={s.status === "running"}
          />
          {s.name}
        </span>
      ))}
    </div>
  );
}
