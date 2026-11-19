import React, { useState } from "react";
import { api } from "../api";
import type { TabProps } from "../App";
import type { CitationReport } from "../types";
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
  StatusPill,
  fmtDuration,
  fmtTime,
} from "./ui";
import { IconExternal, IconQuote } from "./icons";

export function CitationsTab({ projectId, refreshKey, goTo }: TabProps) {
  const { data, loading, error, reload } = useAsync(() => api.citations(projectId), [projectId, refreshKey]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const report: CitationReport | null = data?.report ?? null;
  const created = data?.created_at;

  async function reaudit() {
    setBusy(true);
    setActionError(null);
    const t0 = performance.now();
    try {
      await api.reaudit(projectId);
      reload();
    } catch (e: any) {
      setActionError(e?.message ?? String(e));
    } finally {
      setBusy(false);
      void t0;
    }
  }

  if (loading && !data) return <Spinner label="Loading citation report…" />;
  if (error) return <ErrorNote title="Could not load the citation audit">{error}</ErrorNote>;

  if (!report?.summary) {
    return (
      <EmptyState
        icon={<IconQuote size={22} />}
        title="No citation audit yet"
        description="The citation agent checks every bibliography entry against the DOI resolver and every in-text marker against the bibliography. It never marks a citation verified without a live response."
        action={
          <Button variant="primary" size="sm" onClick={() => goTo("overview")}>
            Run the workflow
          </Button>
        }
      />
    );
  }

  const s = report.summary;
  const good = (s.doi_verified ?? 0) > 0 && (s.entries_with_issues ?? 0) === 0;
  const pct = s.references ? Math.round((s.doi_verified / s.references) * 100) : 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MiniStat label="References" value={s.references} hint={`${s.in_text_markers} in-text markers`} />
        <MiniStat label="DOIs verified" value={s.doi_verified} hint={`${pct}% of references`} tone="ok" />
        <MiniStat
          label="DOI unavailable"
          value={s.doi_unavailable}
          hint="resolver did not answer"
          tone={s.doi_unavailable ? "warn" : "neutral"}
        />
        <MiniStat
          label="DOI failed"
          value={s.doi_failed}
          hint="resolver rejected the DOI"
          tone={s.doi_failed ? "danger" : "neutral"}
        />
      </div>

      <Card>
        <CardHeader
          title="Audit result"
          description={
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Badge tone={good ? "ok" : s.doi_failed ? "danger" : "warn"}>
                {good ? "all references verified" : "issues to review"}
              </Badge>
              {report.draft_version !== undefined && <span>draft v{report.draft_version}</span>}
              {created && <span>audited {fmtTime(created)}</span>}
            </span>
          }
          actions={
            <Button variant="secondary" size="sm" onClick={reaudit} loading={busy}>
              Re-audit now (live DOIs)
            </Button>
          }
        />
        <p className="text-[13px] leading-6 text-ink-600">{report.statement}</p>
        <div className="mt-2">
          <Note tone="neutral">
            <strong>Claim-level check:</strong> {report.claim_level_evidence_check}
          </Note>
        </div>
        {actionError && (
          <div className="mt-2">
            <ErrorNote title="Re-audit failed">{actionError}</ErrorNote>
          </div>
        )}

        {(s.missing_bibliography_entries?.length > 0 ||
          s.unused_bibliography_entries?.length > 0 ||
          s.duplicates?.length > 0) && (
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <IssueList title="Cited but missing" items={s.missing_bibliography_entries} />
            <IssueList title="In bibliography, never cited" items={s.unused_bibliography_entries} />
            <IssueList title="Duplicate keys" items={s.duplicates} />
          </div>
        )}
      </Card>

      <Card padded={false}>
        <div className="px-4 pb-2 pt-4">
          <CardHeader title="Per-reference status" description="One row per bibliography entry, with the live DOI outcome." />
        </div>
        <div className="border-t border-slate-100">
          <table className="table-base">
            <thead>
              <tr>
                <th className="w-16">Key</th>
                <th>Reference</th>
                <th className="w-16">Year</th>
                <th className="w-28">In text</th>
                <th className="w-32">DOI status</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {report.entries.map((e) => (
                <tr key={e.key}>
                  <td className="font-mono text-2xs text-ink-500">{e.key}</td>
                  <td className="text-[13px]">
                    {e.url ? (
                      <a
                        href={e.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 hover:text-primary-700"
                      >
                        {e.title} <IconExternal size={10} />
                      </a>
                    ) : (
                      e.title
                    )}
                  </td>
                  <td className="tabular-nums text-[13px]">{e.year ?? "—"}</td>
                  <td>
                    {e.cited_in_text ? (
                      <Badge tone="ok">cited</Badge>
                    ) : (
                      <Badge tone="warn">not cited</Badge>
                    )}
                  </td>
                  <td>
                    <StatusPill status={e.doi_status} />
                  </td>
                  <td className="text-2xs text-ink-500">
                    {e.issues?.length ? e.issues.join("; ") : <span className="text-ink-300">none</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="text-2xs text-ink-400">
        Verification means the DOI resolver returned a record for that DOI at audit time. It does not mean the paper
        supports the claim it is cited for — that requires reading the paper.
      </p>
    </div>
  );
}

function MiniStat({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: number;
  hint: string;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  const color =
    tone === "ok" ? "text-success-700" : tone === "warn" ? "text-warn-700" : tone === "danger" ? "text-danger-700" : "text-ink-900";
  return (
    <div className="card px-4 py-3">
      <p className="text-[12px] font-medium uppercase tracking-wide text-ink-400">{label}</p>
      <p className={`mt-1 text-[22px] font-semibold leading-tight tabular-nums ${color}`}>{value ?? 0}</p>
      <p className="text-2xs text-ink-400">{hint}</p>
    </div>
  );
}

function IssueList({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-md border border-amber-200 bg-warn-50 px-2.5 py-2">
      <p className="text-2xs font-semibold uppercase tracking-wide text-warn-700">{title}</p>
      <p className="mt-0.5 font-mono text-2xs text-ink-600">{items.join(", ")}</p>
    </div>
  );
}
