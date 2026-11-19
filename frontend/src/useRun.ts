import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamRun } from "./api";
import type { RunDetail } from "./types";

const LIVE_STATUSES = new Set(["pending", "running", "cancelling"]);

export function isLive(status?: string | null) {
  return !!status && LIVE_STATUSES.has(status);
}

export type RunEvent = {
  type: string;
  at: string;
  [key: string]: any;
};

/**
 * Watches one project's current run.
 *
 * The stage list and status come from the backend (polled + pushed over SSE);
 * nothing here invents progress. When the run ends, `onSettled` fires so the
 * project detail (papers, gaps, draft…) can be refetched from the database.
 */
export function useRun(projectId: string | null, onSettled: () => void) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const settledRef = useRef<string | null>(null);
  const runIdRef = useRef<string | null>(null);

  // Load the latest run for the project (or forget the previous project's run).
  useEffect(() => {
    setRun(null);
    setEvents([]);
    setError(null);
    setCancelling(false);
    settledRef.current = null;
    runIdRef.current = null;
    if (!projectId) return;
    let alive = true;
    api
      .listRuns(projectId)
      .then((runs) => {
        if (!alive || !runs?.length) return;
        const latest = runs[0];
        return api.getRun(latest.id).then((d) => {
          if (!alive) return;
          setRun(d);
          runIdRef.current = d.id;
          if (!isLive(d.status)) settledRef.current = d.id;
        });
      })
      .catch(() => {
        /* a project with no runs is not an error */
      });
    return () => {
      alive = false;
    };
  }, [projectId]);

  const runId = run?.id ?? null;
  const live = isLive(run?.status);

  // Poll the run while it is live, and stream its events.
  useEffect(() => {
    if (!runId) return;
    runIdRef.current = runId;
    const dispose = streamRun(runId, (e) => {
      setEvents((prev) => [...prev.slice(-400), { ...e, at: e.at ?? new Date().toISOString() }]);
    });

    let stopped = false;
    let timer: number | undefined;
    const tick = async () => {
      if (stopped) return;
      try {
        const fresh = await api.getRun(runId);
        if (stopped) return;
        setRun(fresh);
        if (!isLive(fresh.status)) {
          if (settledRef.current !== runId) {
            settledRef.current = runId;
            setCancelling(false);
            onSettled();
          }
          return;
        }
        timer = window.setTimeout(tick, 2000);
      } catch (e: any) {
        if (!stopped) setError(e?.message ?? String(e));
        timer = window.setTimeout(tick, 4000);
      }
    };
    timer = window.setTimeout(tick, 600);
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, live]);

  const start = useCallback(
    async (config: Record<string, unknown>) => {
      if (!projectId) return;
      setStarting(true);
      setError(null);
      setEvents([]);
      try {
        const created = await api.startRun(projectId, config);
        const detail = await api.getRun(created.id);
        runIdRef.current = created.id;
        settledRef.current = null;
        setRun(detail);
      } catch (e: any) {
        setError(e?.message ?? String(e));
        throw e;
      } finally {
        setStarting(false);
      }
    },
    [projectId],
  );

  const cancel = useCallback(
    async (reason = "Cancelled from the UI") => {
      if (!runId) return;
      setCancelling(true);
      setError(null);
      try {
        const result = await api.cancelRun(runId, reason);
        const fresh = await api.getRun(runId);
        setRun(fresh);
        if (!result.requested) {
          setError(result.detail || "The run had already finished.");
        }
      } catch (e: any) {
        setError(e?.message ?? String(e));
      } finally {
        setCancelling(false);
      }
    },
    [runId],
  );

  return { run, events, live, start, cancel, cancelling, starting, error, setError };
}
