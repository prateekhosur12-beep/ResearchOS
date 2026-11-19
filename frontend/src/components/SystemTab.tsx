import React from "react";
import type { TabProps } from "../App";
import type { SystemStatus } from "../types";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Divider,
  Dot,
  KeyValue,
  Note,
  Spinner,
  StatusPill,
  fmtDuration,
  fmtTime,
} from "./ui";
import { IconRefresh } from "./icons";

export function SystemTab({
  status,
  onRefreshStatus,
  detail,
}: TabProps & { status: SystemStatus | null; onRefreshStatus: () => void }) {
  if (!status) {
    return (
      <Card>
        <CardHeader
          title="System status"
          description="The UI could not read /api/system/status."
          actions={
            <Button variant="secondary" size="sm" onClick={onRefreshStatus}>
              Retry
            </Button>
          }
        />
        <Spinner label="Waiting for the backend…" />
      </Card>
    );
  }

  const upSources = status.sources.filter((s) => s.status === "ok" || s.status === "available").length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Language model"
            description="Local Ollama only. When it is down the agents say so and fall back to deterministic logic."
            actions={<Badge tone={status.llm.available ? "ok" : "warn"}>{status.llm.available ? "available" : "offline"}</Badge>}
          />
          <KeyValue
            items={[
              { label: "Provider", value: status.llm.provider },
              { label: "Model", value: <span className="font-mono">{status.llm.model}</span> },
              { label: "Endpoint", value: <span className="font-mono">{status.llm.base_url}</span> },
              { label: "Detail", value: status.llm.detail },
              {
                label: "Installed",
                value: status.llm.models_installed?.length ? (
                  <span className="flex flex-wrap gap-1">
                    {status.llm.models_installed.map((m) => (
                      <Badge key={m} tone="neutral">
                        {m}
                      </Badge>
                    ))}
                  </span>
                ) : (
                  "none reported"
                ),
              },
            ]}
          />
          {!status.llm.available && (
            <div className="mt-3">
              <Note tone="warn">
                Every agent is currently running on its deterministic path. Draft text is template-generated from
                retrieved evidence and is labelled as such — no model output is fabricated.
              </Note>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Database"
            description={status.database?.detail}
            actions={<Badge tone={status.database?.connected ? "ok" : "danger"}>{status.database?.backend}</Badge>}
          />
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(status.database?.counts ?? {}).map(([k, v]) => (
              <div key={k} className="rounded-md border border-slate-200 bg-slate-50/60 px-2.5 py-1.5">
                <p className="text-2xs uppercase tracking-wide text-ink-400">{k}</p>
                <p className="text-[15px] font-semibold tabular-nums text-ink-900">{v}</p>
              </div>
            ))}
          </div>
          <Divider />
          <KeyValue
            items={[
              { label: "Latency", value: fmtDuration(status.database?.latency_ms) },
              { label: "Embeddings", value: `${status.embedding?.model} (${status.embedding?.enabled ? "local" : "fallback: " + status.embedding?.fallback})` },
              { label: "Uptime", value: fmtDuration((status.uptime_s ?? 0) * 1000) },
              { label: "Version", value: status.version },
            ]}
          />
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Scholarly sources"
          description={`${upSources}/${status.sources.length} answering live probes — this is a real request per source, made just now.`}
          actions={
            <Button variant="secondary" size="sm" icon={<IconRefresh size={13} />} onClick={onRefreshStatus}>
              Probe again
            </Button>
          }
        />
        <table className="table-base">
          <thead>
            <tr>
              <th>Source</th>
              <th className="w-28">Status</th>
              <th className="w-24 text-right">Latency</th>
              <th className="w-36">Checked</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {status.sources.map((s) => (
              <tr key={s.source}>
                <td className="font-medium text-[13px]">{s.source}</td>
                <td>
                  <StatusPill status={s.status} />
                </td>
                <td className="text-right text-2xs tabular-nums">{fmtDuration(s.latency_ms)}</td>
                <td className="text-2xs text-ink-400">{fmtTime(s.checked_at)}</td>
                <td className="max-w-[380px] text-2xs text-ink-500">{s.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Tool layer"
            description={`${status.mcp?.tool_count ?? 0} tools over ${status.tool_transport}`}
            actions={<Badge tone={status.mcp?.ok ? "ok" : status.mcp?.ok === null ? "warn" : "danger"}>
              {status.mcp?.ok ? "MCP connected" : status.mcp?.ok === null ? "MCP unknown" : "MCP down"}
            </Badge>}
          />
          {status.mcp?.error && <Note tone="warn">MCP error: {status.mcp.error}</Note>}
          {status.mcp?.server && (
            <p className="mt-2 font-mono text-2xs text-ink-400">
              {Object.entries(status.mcp.server)
                .map(([k, v]) => `${k}=${v}`)
                .join(" ")}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-1">
            {(status.mcp?.tools ?? status.tools ?? []).map((t) => (
              <span key={t} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-2xs text-ink-600">
                {t}
              </span>
            ))}
          </div>
          {status.mcp?.note && <p className="mt-2 text-2xs text-ink-400">{status.mcp.note}</p>}
        </Card>

        <Card>
          <CardHeader title="Runtime configuration" description="Effective settings of this backend process." />
          <div className="max-h-[260px] overflow-y-auto">
            <KeyValue
              items={Object.entries(status.config ?? {}).map(([k, v]) => ({
                label: k.replace(/_/g, " "),
                value: (
                  <span className="font-mono text-2xs">
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </span>
                ),
              }))}
            />
          </div>
        </Card>
      </div>

      {detail && (
        <Card>
          <CardHeader title="This project" description="Stored settings for the selected project." />
          <KeyValue
            items={[
              { label: "Project id", value: <span className="font-mono text-2xs">{detail.id}</span> },
              { label: "Domain", value: detail.domain },
              { label: "Created", value: fmtTime(detail.created_at) },
              { label: "Updated", value: fmtTime(detail.updated_at) },
              {
                label: "Counts",
                value: `${detail.paper_count} papers · ${detail.gap_count} gaps · ${detail.idea_count} ideas · ${detail.draft_count} drafts · ${detail.run_count} runs`,
              },
              { label: "Active run", value: detail.active_run_id ?? "none" },
            ]}
          />
        </Card>
      )}

      <p className="flex items-center gap-1.5 text-2xs text-ink-400">
        <Dot tone="muted" /> Status values are derived from live checks made at page load, not from cached constants.
      </p>
    </div>
  );
}
