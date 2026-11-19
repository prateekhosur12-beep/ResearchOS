import React, { useState } from "react";
import { api } from "../api";
import type { TabProps } from "../App";
import { useAsync } from "../hooks";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorNote,
  Note,
  Spinner,
  fmtTime,
} from "./ui";
import { IconDownload, IconExternal } from "./icons";

const LABELS: Record<string, string> = {
  papers_csv: "Papers (CSV)",
  papers_md: "Paper table (Markdown)",
  gaps_md: "Gaps & ideas (Markdown)",
  manuscript_md: "Manuscript (Markdown)",
  manuscript_docx: "Manuscript (Word .docx)",
  citations_md: "Citation audit (Markdown)",
  citations_csv: "Citation audit (CSV)",
  radar_md: "Venues & funding (Markdown)",
  full_report_md: "Full report (Markdown)",
};

export function ExportsTab({ projectId, refreshKey, goTo }: TabProps) {
  const { data, loading, error, reload } = useAsync(() => api.exports(projectId), [projectId, refreshKey]);
  const approvals = useAsync(() => api.approvals(projectId), [projectId, refreshKey]);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const kinds: string[] = data?.available_kinds ?? [];
  const exports: any[] = data?.exports ?? [];
  const requiresApproval = approvals.data?.required_before_export ?? true;
  const draftApproved = (approvals.data?.approvals ?? []).some(
    (a: any) => a.artifact_type === "draft" && a.status === "approved",
  );

  async function create(kind: string) {
    setBusy(kind);
    setActionError(null);
    try {
      await api.createExport(projectId, kind);
      reload();
    } catch (e: any) {
      setActionError(e?.message ?? String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="Exports"
          description="Generated from the stored project data. Nothing is written into an export that is not in the database."
          actions={
            <Button variant="ghost" size="sm" onClick={reload}>
              Refresh
            </Button>
          }
        />

        {requiresApproval && (
          <div className="mb-3">
            <Note tone={draftApproved ? "ok" : "warn"}>
              {draftApproved
                ? "Draft approved — manuscript exports are unlocked."
                : "Approval is required before manuscript exports. Approve the draft on the Draft tab first; the backend will refuse otherwise."}
              {!draftApproved && (
                <button className="ml-1 font-medium underline" onClick={() => goTo("draft")}>
                  Review draft
                </button>
              )}
            </Note>
          </div>
        )}

        {actionError && (
          <div className="mb-3">
            <ErrorNote title="Export failed">{actionError}</ErrorNote>
          </div>
        )}
        {error && <ErrorNote>{error}</ErrorNote>}
        {loading && !data && <Spinner label="Loading exports…" />}

        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {kinds.map((k) => (
            <div key={k} className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-ink-800">{LABELS[k] ?? k}</p>
                <p className="font-mono text-2xs text-ink-400">{k}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon={<IconDownload size={13} />}
                onClick={() => create(k)}
                loading={busy === k}
              >
                Build
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <Card padded={false}>
        <div className="px-4 pb-2 pt-4">
          <CardHeader title="Generated files" description={`${exports.length} export(s) on disk`} />
        </div>
        <div className="border-t border-slate-100">
          <table className="table-base">
            <thead>
              <tr>
                <th>File</th>
                <th className="w-40">Kind</th>
                <th className="w-24 text-right">Size</th>
                <th className="w-36">Created</th>
                <th className="w-24">Approved by</th>
                <th className="w-16"></th>
              </tr>
            </thead>
            <tbody>
              {exports.map((e) => (
                <tr key={e.id}>
                  <td className="font-mono text-2xs text-ink-700">{e.filename}</td>
                  <td>
                    <Badge tone="neutral">{LABELS[e.kind] ?? e.kind}</Badge>
                  </td>
                  <td className="text-right text-2xs tabular-nums">{(e.size_bytes ?? 0).toLocaleString()} B</td>
                  <td className="text-2xs text-ink-400">{fmtTime(e.created_at)}</td>
                  <td className="text-2xs text-ink-500">{e.approved_by ?? "—"}</td>
                  <td>
                    <a
                      href={e.download_url}
                      className="inline-flex items-center gap-0.5 text-2xs text-primary-700 hover:underline"
                      download
                    >
                      download <IconExternal size={10} />
                    </a>
                  </td>
                </tr>
              ))}
              {exports.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-[13px] text-ink-400">
                    No files yet — build one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
