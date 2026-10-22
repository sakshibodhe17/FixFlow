import { useCallback, useEffect, useRef, useState } from 'react';
import api, { errorMessage } from './api';

/** GET an endpoint. `pollMs` re-fetches quietly in the background (real-time tracking). */
export function useApi(url, { params, pollMs, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(enabled);
  const key = JSON.stringify(params || {});
  const alive = useRef(true);

  const load = useCallback(async (quiet = false) => {
    if (!enabled || !url) return;
    if (!quiet) setLoading(true);
    try {
      const res = await api.get(url, { params: JSON.parse(key) });
      if (alive.current) { setData(res.data); setError(null); }
    } catch (e) {
      if (alive.current && !quiet) setError(errorMessage(e));
    } finally {
      if (alive.current && !quiet) setLoading(false);
    }
  }, [url, key, enabled]);

  useEffect(() => {
    alive.current = true;
    load();
    if (!pollMs) return () => { alive.current = false; };
    const id = setInterval(() => { if (document.visibilityState === 'visible') load(true); }, pollMs);
    return () => { alive.current = false; clearInterval(id); };
  }, [load, pollMs]);

  return { data, error, loading, reload: load, setData };
}

/** Wrap an async action with busy/error state. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = useCallback(async (fn) => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(errorMessage(e));
      throw e;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

/** Re-render every `ms` so countdowns stay live. */
export function useTicker(ms = 30000) {
  const [, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((t) => t + 1), ms);
    return () => clearInterval(id);
  }, [ms]);
}
