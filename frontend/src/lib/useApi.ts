import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage } from "./api";

/** Load data for a screen. Keeps the previous data visible while refetching (no skeleton flash). */
export function useApi<T>(path: string | null, query?: Record<string, unknown>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const key = path ? path + JSON.stringify(query ?? {}) : null;
  const latest = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const ticket = ++latest.current;
    setLoading(true);
    try {
      const result = await api<T>(path, { query });
      if (ticket === latest.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (ticket === latest.current) setError(errorMessage(e));
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
  }, [key]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}
