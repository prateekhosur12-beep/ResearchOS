import { useCallback, useEffect, useRef, useState } from "react";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const run = useCallback(() => {
    setLoading(true);
    setError(null);
    fn()
      .then((res) => {
        if (alive.current) setData(res);
      })
      .catch((e) => {
        if (alive.current) setError(e?.message ?? String(e));
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    alive.current = true;
    run();
    return () => {
      alive.current = false;
    };
  }, [run]);

  return { data, loading, error, reload: run, setData };
}

export function useNow(intervalMs = 1000) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}
