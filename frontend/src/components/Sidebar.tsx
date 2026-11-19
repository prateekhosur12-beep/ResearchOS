import React, { useMemo, useState } from "react";
import type { Project, SystemStatus } from "../types";
import { Badge, Dot, relTime, statusTone } from "./ui";
import { IconLogo, IconPlus, IconSearch, IconSpinner, IconTrash } from "./icons";

export function Sidebar({
  projects,
  selectedId,
  onSelect,
  onNew,
  onDelete,
  status,
  loading,
}: {
  projects: Project[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (p: Project) => void;
  status: SystemStatus | null;
  loading: boolean;
}) {
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(needle) ||
        p.topic.toLowerCase().includes(needle) ||
        p.domain.toLowerCase().includes(needle),
    );
  }, [projects, q]);

  const dep = (label: string, ok: boolean | null | undefined, detail?: string) => (
    <div className="flex items-center gap-2.5" title={detail}>
      <Dot tone={ok === true ? "ok" : ok === false ? "danger" : "muted"} />
      <span className="text-[12px] font-medium text-slate-300">{label}</span>
      <span className={`ml-auto text-[11px] font-semibold text-slate-400`}>
        {ok === true ? "up" : ok === false ? "down" : "?"}
      </span>
    </div>
  );

  const sources = status?.sources ?? [];
  const sourcesUp = sources.filter((s) => s.status === "ok" || s.status === "available").length;

  return (
    <aside className="researchos-sidebar flex h-full w-[320px] shrink-0 flex-col">
      <div className="flex items-center gap-3 px-5 pb-5 pt-5">
        <IconLogo size={28} />
        <div className="min-w-0">
          <p className="truncate text-[17px] font-bold leading-tight text-white">ResearchOS</p>
          <p className="truncate text-[12px] text-slate-400">Agentic research workspace</p>
        </div>
      </div>

      <div className="px-4">
        <button
          onClick={onNew}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#ff8736] text-[14px] font-semibold text-white shadow-sm transition-colors hover:bg-[#f47725]"
        >
          <IconPlus size={15} /> New project
        </button>
      </div>

      <div className="px-4 pt-4">
        <div className="relative">
          <IconSearch size={14} className="absolute left-2.5 top-2.5 text-ink-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search projects"
            className="h-10 w-full rounded-lg border border-slate-600 bg-[#202b3d] pl-9 pr-3 text-[14px] text-white placeholder:text-slate-400 focus:border-[#ff8736] focus:outline-none focus:ring-2 focus:ring-orange-500/20"
          />
        </div>
      </div>

      <div className="mt-5 flex items-center justify-between px-5">
        <span className="section-title">Projects</span>
        <span className="text-2xs text-ink-400">{projects.length}</span>
      </div>

      <nav className="mt-2 flex-1 overflow-y-auto px-3 pb-4">
        {loading && (
          <div className="flex items-center gap-2 px-2 py-3 text-[13px] text-ink-400">
            <IconSpinner size={13} /> Loading…
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <p className="px-2 py-3 text-[13px] text-ink-400">
            {projects.length ? "No project matches that search." : "No projects yet. Create one to start."}
          </p>
        )}
        <ul className="space-y-1.5">
          {filtered.map((p) => {
            const active = p.id === selectedId;
            const tone = statusTone(p.last_run_status);
            return (
              <li key={p.id}>
                <div
                  className={`group relative flex cursor-pointer items-start gap-3 rounded-lg px-3 py-3 ${
                    active ? "bg-[#263449] shadow-sm ring-1 ring-[#ff8736]/70" : "hover:bg-[#1c293b]"
                  }`}
                  onClick={() => onSelect(p.id)}
                >
                  <span className="mt-1.5 flex h-1.5 w-4 items-center">
                    <Dot tone={tone} pulse={p.last_run_status === "running" || p.last_run_status === "cancelling"} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-[14px] leading-5 ${active ? "font-semibold text-white" : "font-medium text-slate-200"}`}
                      title={p.topic}
                    >
                      {p.name}
                    </p>
                    <p className="mt-0.5 flex items-center gap-1.5 truncate text-[12px] text-slate-400">
                      <span className="truncate">{p.domain.replace(/_/g, " ")}</span>
                      <span>·</span>
                      <span className="tabular-nums">{p.paper_count} papers</span>
                      {p.last_run_status && (
                        <>
                          <span>·</span>
                          <span className="truncate">{p.last_run_status.replace(/_/g, " ")}</span>
                        </>
                      )}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(p);
                    }}
                    className="mt-0.5 hidden rounded p-1 text-ink-300 hover:bg-danger-50 hover:text-danger-600 group-hover:block"
                    title="Delete project"
                  >
                    <IconTrash size={13} />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-slate-700 px-5 py-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="section-title">Environment</span>
          {status ? (
            <Badge tone={status.llm.available ? "ok" : "warn"}>
              {status.llm.available ? "LLM ready" : "LLM offline"}
            </Badge>
          ) : (
            <span className="text-2xs text-ink-400">checking…</span>
          )}
        </div>
        {status ? (
          <div className="space-y-2">
            {dep("Ollama", status.llm.available, `${status.llm.model} @ ${status.llm.base_url}`)}
            {dep("Database", status.database?.connected, status.database?.detail)}
            {dep(
              `Sources ${sourcesUp}/${sources.length}`,
              sourcesUp === sources.length && sources.length > 0,
              sources.map((s) => `${s.source}: ${s.status}`).join(", "),
            )}
            {dep("MCP tools", status.mcp?.ok ?? null, status.mcp?.error ?? `${status.mcp?.tool_count ?? 0} tools`)}
          </div>
        ) : (
          <p className="text-2xs text-ink-400">Status unavailable</p>
        )}
        {projects.length > 0 && (
          <p className="mt-3 text-[11px] text-slate-500">last activity {relTime(projects[0].updated_at)}</p>
        )}
      </div>
    </aside>
  );
}
