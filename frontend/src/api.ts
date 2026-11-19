import type { Project, ProjectDetail, RunDetail, SystemStatus, TracePayload } from "./types";

const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(detail);
    (err as any).status = res.status;
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string; uptime_s: number }>("/api/health"),
  systemStatus: () => request<SystemStatus>("/api/system/status"),
  domains: () => request<{ domains: any[]; default: string }>("/api/system/domains"),

  listProjects: () => request<Project[]>("/api/projects"),
  createProject: (body: {
    name: string;
    topic: string;
    domain?: string;
    research_instructions?: string;
    research_questions?: string[];
  }) => request<Project>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => request<ProjectDetail>(`/api/projects/${id}`),
  patchProject: (id: string, body: Record<string, unknown>) =>
    request<Project>(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  projectQueries: (id: string, refresh = true) =>
    request<any>(`/api/projects/${id}/queries?refresh=${refresh ? "true" : "false"}`),
  deleteProject: (id: string) => request<any>(`/api/projects/${id}`, { method: "DELETE" }),

  startRun: (projectId: string, config: Record<string, unknown>) =>
    request<{ id: string; stream: string; status?: string }>(`/api/projects/${projectId}/runs`, {
      method: "POST",
      body: JSON.stringify(config),
    }),
  listRuns: (projectId: string) => request<any[]>(`/api/projects/${projectId}/runs`),
  getRun: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),
  cancelRun: (runId: string, reason = "cancelled from the UI") =>
    request<{ requested: boolean; cancelled: boolean; status: string; detail: string }>(
      `/api/runs/${runId}/cancel`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
  trace: (runId: string) => request<TracePayload>(`/api/runs/${runId}/trace`),

  papers: (projectId: string, params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request<any>(`/api/projects/${projectId}/papers${qs ? `?${qs}` : ""}`);
  },
  patchPaper: (projectId: string, paperId: string, body: Record<string, unknown>) =>
    request<any>(`/api/projects/${projectId}/papers/${paperId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  gaps: (projectId: string) => request<any>(`/api/projects/${projectId}/gaps`),
  ideas: (projectId: string) => request<any>(`/api/projects/${projectId}/ideas`),
  draft: (projectId: string) => request<any>(`/api/projects/${projectId}/draft`),
  editSection: (projectId: string, section: string, markdown: string) =>
    request<any>(`/api/projects/${projectId}/draft/section`, {
      method: "PATCH",
      body: JSON.stringify({ section, markdown }),
    }),
  regenerateSection: (projectId: string, section: string, feedback?: string) =>
    request<any>(`/api/projects/${projectId}/draft/regenerate`, {
      method: "POST",
      body: JSON.stringify({ section, feedback }),
    }),
  citations: (projectId: string) => request<any>(`/api/projects/${projectId}/citations`),
  reaudit: (projectId: string) =>
    request<any>(`/api/projects/${projectId}/citations/audit`, { method: "POST" }),
  radar: (projectId: string) => request<any>(`/api/projects/${projectId}/radar`),
  deepResearch: (projectId: string) => request<any>(`/api/projects/${projectId}/deep-research`),
  retrieval: (projectId: string, query: string, limit = 8) =>
    request<any>(`/api/projects/${projectId}/retrieval/search`, {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    }),

  approvals: (projectId: string) => request<any>(`/api/projects/${projectId}/approvals`),
  decide: (approvalId: string, decision: "approved" | "rejected", note?: string) =>
    request<any>(`/api/approvals/${approvalId}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision, actor: "reviewer", note }),
    }),
  audit: (projectId: string) => request<any>(`/api/projects/${projectId}/audit`),
  exports: (projectId: string) => request<any>(`/api/projects/${projectId}/exports`),
  createExport: (projectId: string, kind: string) =>
    request<any>(`/api/projects/${projectId}/exports`, {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
  toolInvocations: (projectId: string) => request<any[]>(`/api/projects/${projectId}/tool-invocations`),
  labs: () => request<any>("/api/labs"),
};

/** Subscribe to the real SSE workflow stream. Returns a disposer. */
export function streamRun(
  runId: string,
  onEvent: (e: any) => void,
  onError?: (e: Event) => void,
): () => void {
  const es = new EventSource(`/api/runs/${runId}/events`);
  es.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data.type === "stream_end") {
        es.close();
        onEvent(data);
        return;
      }
      onEvent(data);
    } catch {
      /* ignore malformed frame */
    }
  };
  es.onerror = (e) => {
    onError?.(e);
    es.close();
  };
  return () => es.close();
}
