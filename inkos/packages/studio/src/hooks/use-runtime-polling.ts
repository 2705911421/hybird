import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJson } from "./use-api";

export function useRuntimePolling<T>(path: string, options: { readonly intervalMs?: number; readonly active?: boolean } = {}) {
  const intervalMs = options.intervalMs ?? 30_000;
  const active = options.active ?? true;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const failures = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refetch = useCallback(async () => {
    if (!path) return false;
    try {
      const value = await fetchJson<T>(path);
      failures.current = 0;
      setData(value);
      setError(null);
      return true;
    } catch (cause) {
      failures.current += 1;
      setError(cause instanceof Error ? cause.message : String(cause));
      return false;
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (!active || !path) return;
    let cancelled = false;
    const schedule = async () => {
      if (cancelled) return;
      if (document.visibilityState === "hidden") {
        timer.current = setTimeout(schedule, intervalMs);
        return;
      }
      await refetch();
      if (cancelled) return;
      const backoff = Math.min(intervalMs * (2 ** failures.current), 5 * 60_000);
      timer.current = setTimeout(schedule, backoff);
    };
    void schedule();
    const onVisibility = () => {
      if (document.visibilityState === "visible" && timer.current) {
        clearTimeout(timer.current);
        void schedule();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [active, intervalMs, path, refetch]);

  return { data, loading, error, refetch };
}
