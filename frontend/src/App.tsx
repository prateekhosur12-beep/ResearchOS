import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { useRun, isLive } from "./useRun";
import type { DomainPack, Project, ProjectDetail, SystemStatus } from "./types";
import { Sidebar } from "./components/Sidebar";
import { NewProjectModal } from "./components/NewProjectModal";
import { StageChips } from "./components/StageTimeline";
import { OverviewTab } from "./components/OverviewTab";
import { LiteratureTab } from "./components/LiteratureTab";
import { GapsTab } from "./components/GapsTab";
import { DraftTab } from "./components/DraftTab";
import { CitationsTab } from "./components/CitationsTab";
import { RadarTab } from "./components/RadarTab";
import { TraceTab } from "./components/TraceTab";
import { ExportsTab } from "./components/ExportsTab";
import { SystemTab } from "./components/SystemTab";
import { Badge, Button, Dot, ErrorNote, Spinner, StatusPill, relTime } from "./components/ui";
import { IconBeaker, IconBranch, IconDoc, IconDownload, IconList, IconQuote, IconRadar, IconRefresh, IconServer, IconSpinner, IconStop } from "./components/icons";

export type TabKey =
  | "overview"
  | "literature"
  | "gaps"
  | "draft"
  | "citations"
  | "radar"
  | "trace"
  | "exports"
  | "system";

export interface TabProps {
  projectId: string;
  detail: ProjectDetail | null;
  refreshKey: number;
  onReload: () => void;
  goTo: (tab: TabKey) => void;
}

const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
  { key: "overview", label: "Overview", icon: <IconList size={14} /> },
  { key: "literature", label: "Literature", icon: <IconDoc size={14} /> },
  { key: "gaps", label: "Gaps & Ideas", icon: <IconBranch size={14} /> },
  { key: "draft", label: "Draft", icon: <IconBeaker size={14} /> },
  { key: "citations", label: "Citations", icon: <IconQuote size={14} /> },
  { key: "radar", label: "Venues & funding", icon: <IconRadar size={14} /> },
  { key: "trace", label: "Trace & audit", icon: <IconList size={14} /> },
  { key: "exports", label: "Exports", icon: <IconDownload size={14} /> },
  { key: "system", label: "System", icon: <IconServer size={14} /> },
];

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");
  const [newOpen, setNewOpen] = useState(false);
  const [domains, setDomains] = useState<DomainPack[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  // Presentation-only preference: does not affect API calls or research workflow.
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    try {
      return window.localStorage.getItem("researchos-theme") === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem("researchos-theme", theme);
    } catch {
      // Theme still works for the current session if storage is unavailable.
    }
  }, [theme]);

  /* ------------------------------------------------------------ boot data */

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.systemStatus();
      setStatus(s);
      setStatusError(null);
    } catch (e: any) {
      setStatus(null);
      setStatusError(e?.message ?? String(e));
    }
  }, []);

  const loadProjects = useCallback(async (select?: string | null) => {
    setProjectsLoading(true);
    try {
      const list = await api.listProjects();
      setProjects(list);
      setSelectedId((prev) => {
        const wanted = select ?? prev;
        if (wanted && list.some((p) => p.id === wanted)) return wanted;
        return list[0]?.id ?? null;
      });
    } catch {
      setProjects([]);
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
    loadStatus();
    api
      .domains()
      .then((d) => setDomains(d.domains ?? []))
      .catch(() => setDomains([]));
    const id = window.setInterval(loadStatus, 20000);
    return () => window.clearInterval(id);
  }, [loadProjects, loadStatus]);

  const loadDetail = useCallback(async (id: string) => {
    setDetailLoading(true);
    try {
      const d = await api.getProject(id);
      setDetail(d);
      setDetailError(null);
    } catch (e: any) {
      setDetail(null);
      setDetailError(e?.message ?? String(e));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    loadDetail(selectedId);
  }, [selectedId, loadDetail, refreshKey]);

  const reloadAll = useCallback(() => {
    if (selectedId) loadDetail(selectedId);
    loadProjects(selectedId);
    setRefreshKey((k) => k + 1);
  }, [selectedId, loadDetail, loadProjects]);

  const runCtl = useRun(selectedId, reloadAll);

  /* ----------------------------------------------------------- selection */

  const current = projects.find((p) => p.id === selectedId) ?? null;
  const project = detail ?? current;

  async function handleDelete(p: Project) {
    if (!window.confirm(`Delete "${p.name}" and everything derived from it?`)) return;
    try {
      await api.deleteProject(p.id);
      if (p.id === selectedId) {
        setSelectedId(null);
        setDetail(null);
      }
      loadProjects(null);
    } catch (e: any) {
      window.alert(`Delete failed: ${e?.message ?? e}`);
    }
  }

  const liveVideo = runCtl.run ? isLive(runCtl.run.status) : false;
  const stages = runCtl.run?.stages ?? [];
  const completedStages = useMemo(() => stages.filter((s) => s.status === "completed").length, [stages]);
  const runningStage = stages.find((s) => s.status === "running");

  const tabProps: TabProps = {
    projectId: selectedId ?? "",
    detail,
    refreshKey,
    onReload: reloadAll,
    goTo: setTab,
  };

  /* ---------------------------------------------------------------- view */

  return (
    <div data-theme={theme} className="researchos-shell flex h-screen w-full overflow-hidden bg-white">
      <Sidebar
        projects={projects}
        selectedId={selectedId}
        onSelect={(id) => {
          setSelectedId(id);
          setTab("overview");
        }}
        onNew={() => setNewOpen(true)}
        onDelete={handleDelete}
        status={status}
        loading={projectsLoading}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        {/* header */}
        <header className="shrink-0 border-b border-slate-200 bg-white/95 px-6 pt-3 backdrop-blur">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              {project ? (
                <>
                  <div className="flex items-center gap-2">
                    <h1 className="truncate text-[17px] font-semibold text-ink-900">{project.name}</h1>
                    <Badge tone="neutral">{project.domain.replace(/_/g, " ")}</Badge>
                    {project.last_run_status && <StatusPill status={project.last_run_status} />}
                  </div>
                  <p className="mt-0.5 line-clamp-1 max-w-[70ch] text-[13px] text-ink-500" title={project.topic}>
                    {project.topic}
                  </p>
                </>
              ) : (
                <h1 className="text-[17px] font-semibold text-ink-900">Research Assistant</h1>
              )}
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                className="theme-toggle"
                onClick={() => setTheme((value) => (value === "light" ? "dark" : "light"))}
                aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
                title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
              >
                <span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>
                <span className="theme-toggle-label">{theme === "light" ? "Dark mode" : "Light mode"}</span>
              </button>
              <Button
                variant="ghost"
                size="sm"
                icon={<IconRefresh size={14} />}
                onClick={reloadAll}
                title="Reload project data"
              >
                Refresh
              </Button>
              {liveVideo && runCtl.run ? (
                <Button
                  variant="danger"
                  icon={runCtl.cancelling ? <IconSpinner size={14} /> : <IconStop size={14} />}
                  onClick={() => runCtl.cancel("Cancelled from the UI")}
                  disabled={runCtl.cancelling}
                >
                  {runCtl.cancelling ? "Cancelling…" : "Cancel run"}
                </Button>
              ) : (
                <Badge tone={stages.length ? "neutral" : "muted"}>
                  <Dot tone={project?.last_run_status ? (project.last_run_status === "completed" ? "ok" : "warn") : "muted"} />
                  {project?.last_run_status
                    ? `last run ${project.last_run_status.replace(/_/g, " ")} · ${relTime(runCtl.run?.created_at)}`
                    : "no runs yet"}
                </Badge>
              )}
            </div>
          </div>

          {/* live run strip */}
          {liveVideo && runCtl.run && (
            <div className="mt-2 flex items-center gap-2 rounded-md border border-primary-100 bg-primary-50/60 px-3 py-1.5">
              <IconSpinner size={13} className="text-primary-700" />
              <span className="text-[12.5px] font-medium text-primary-700">
                {runningStage ? runningStage.name : "starting…"}
              </span>
              <span className="text-2xs text-ink-400">
                stage {completedStages + (runningStage ? 1 : 0)} of {stages.length || 12}
              </span>
              <div className="mx-2 h-1 flex-1 overflow-hidden rounded-full bg-primary-100">
                <div
                  className="h-full rounded-full bg-primary-600 transition-all"
                  style={{ width: `${stages.length ? (completedStages / stages.length) * 100 : 2}%` }}
                />
              </div>
              <span className="text-2xs text-ink-400">{runCtl.run.status}</span>
            </div>
          )}

          {/* tabs */}
          <nav className="mt-2 flex items-center gap-0.5">
            {TABS.map((t) => {
              const active = t.key === tab;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`relative flex items-center gap-1.5 px-2.5 py-2 text-[13px] font-medium transition-colors ${
                    active ? "text-ink-900" : "text-ink-500 hover:text-ink-800"
                  }`}
                >
                  <span className={active ? "text-primary-600" : "text-ink-400"}>{t.icon}</span>
                  {t.label}
                  {active && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-t bg-primary-600" />}
                </button>
              );
            })}
          </nav>
        </header>

        {/* body */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50/40">
          <div className="mx-auto w-full max-w-[1180px] px-6 py-5">
            {statusError && !status && (
              <div className="mb-4">
                <ErrorNote title="Backend unreachable">
                  {statusError}. The UI is running but the API at /api is not answering.
                </ErrorNote>
              </div>
            )}
            {runCtl.error && (
              <div className="mb-4">
                <ErrorNote title="Run control">{runCtl.error}</ErrorNote>
              </div>
            )}

            {detailError && (
              <div className="mb-4">
                <ErrorNote title="Could not load project">{detailError}</ErrorNote>
              </div>
            )}

            {!selectedId ? (
              <EmptyWorkspace
                onCreate={() => setNewOpen(true)}
                projectsExist={projects.length > 0}
                loading={projectsLoading}
              />
            ) : detailLoading && !detail ? (
              <Spinner label="Loading project…" />
            ) : (
              <>
                {tab === "overview" && (
                  <OverviewTab
                    {...tabProps}
                    run={runCtl.run}
                    events={runCtl.events}
                    onStart={runCtl.start}
                    onCancel={runCtl.cancel}
                    starting={runCtl.starting}
                    cancelling={runCtl.cancelling}
                    runError={runCtl.error}
                  />
                )}
                {tab === "literature" && <LiteratureTab {...tabProps} />}
                {tab === "gaps" && <GapsTab {...tabProps} />}
                {tab === "draft" && <DraftTab {...tabProps} />}
                {tab === "citations" && <CitationsTab {...tabProps} />}
                {tab === "radar" && <RadarTab {...tabProps} />}
                {tab === "trace" && <TraceTab {...tabProps} run={runCtl.run} />}
                {tab === "exports" && <ExportsTab {...tabProps} />}
                {tab === "system" && <SystemTab {...tabProps} status={status} onRefreshStatus={loadStatus} />}
              </>
            )}
          </div>
        </div>

        {/* footer strip */}
        <footer className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-white px-6 py-1.5 text-2xs text-ink-400">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5">
              <Dot tone={status?.llm.available ? "ok" : "warn"} />
              {status ? (status.llm.available ? `Ollama ${status.llm.model}` : "LLM unavailable — deterministic path") : "LLM unknown"}
            </span>
            {status && (
              <>
                <span className="flex items-center gap-1.5">
                  <Dot tone={status.database?.connected ? "ok" : "danger"} />
                  {status.database?.backend ?? "database"}
                </span>
                {stages.length > 0 && <StageChips stages={stages} />}
              </>
            )}
          </div>
          <span>
            {status ? `v${status.version} · MCP ${status.mcp?.tool_count ?? 0} tools · ${status.tool_transport}` : ""}
          </span>
        </footer>
      </main>

      <NewProjectModal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        domains={domains}
        defaultDomain={status?.config?.default_domain ?? "auto"}
        onCreated={(p) => {
          setNewOpen(false);
          setProjects((prev) => [p, ...prev]);
          setSelectedId(p.id);
          setTab("overview");
          loadProjects(p.id);
        }}
      />
    </div>
  );
}

function EmptyWorkspace({
  onCreate,
  projectsExist,
  loading,
}: {
  onCreate: () => void;
  projectsExist: boolean;
  loading: boolean;
}) {
  if (loading) return <Spinner label="Loading workspace…" />;
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
        <IconBeaker size={24} />
      </div>
      <h2 className="text-lg font-semibold text-ink-900">
        {projectsExist ? "Select a project" : "Create your first research project"}
      </h2>
      <p className="mt-1 max-w-md text-[13.5px] text-ink-500">
        {projectsExist
          ? "Pick a project from the sidebar to see its literature, gaps, draft and run trace."
          : "Give the project a short topic and an optional brief. The agents will search OpenAlex, Crossref and arXiv, then build gaps, ideas, a draft and a citation audit from what they actually found."}
      </p>
      <Button variant="primary" className="mt-4" onClick={onCreate}>
        New project
      </Button>
    </div>
  );
}
