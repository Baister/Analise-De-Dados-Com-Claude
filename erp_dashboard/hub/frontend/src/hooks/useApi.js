import { useState, useEffect, useCallback, useMemo } from 'react';

export async function apiFetch(path, opts = {}) {
  const token = localStorage.getItem('erp_token');
  const headers = { ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(path, { ...opts, headers });

  if (res.status === 401) {
    localStorage.removeItem('erp_token');
    localStorage.removeItem('erp_tabs');
    location.reload();
    return null;
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

// useDados: hook para páginas que consomem um único bot.
// refreshTrigger: qualquer valor — mudança dispara refetch.
// Polling a cada 60s como fallback quando SSE não disparou.
export function useDados(botKey, refreshTrigger) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDados = useCallback(async () => {
    if (!botKey) return;
    setLoading(true);
    try {
      const d = await apiFetch(`/dados/${botKey}`);
      setData(d ?? null);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [botKey]);

  // Fetch on mount and when SSE fires (refreshTrigger changes)
  useEffect(() => { fetchDados(); }, [fetchDados, refreshTrigger]);

  // Polling fallback: re-fetch every 60s in case SSE is unavailable
  useEffect(() => {
    const id = setInterval(fetchDados, 60_000);
    return () => clearInterval(id);
  }, [fetchDados]);

  // Bot hasn't finished first analysis yet (resultado still empty {})
  const isEmpty = data !== null && typeof data === 'object' && Object.keys(data).length === 0;

  return { data, loading, error, refetch: fetchDados, isEmpty };
}

// useFilteredDados: like useDados but with optional server-side filters.
// When filters is non-empty, calls /dados/{botKey}/filtered?... (no cache, on-demand).
// When filters is empty, calls /dados/{botKey} (uses cached bot result).
// filters: plain object with API param names, e.g. { vendedor: 'João', marca: 'Samsung' }
export function useFilteredDados(botKey, filters = {}, refreshTrigger) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const filterStr = useMemo(() => {
    const entries = Object.entries(filters ?? {}).filter(([, v]) => v != null && v !== '');
    if (!entries.length) return '';
    return new URLSearchParams(entries).toString();
  }, [filters]);

  const fetchDados = useCallback(async () => {
    if (!botKey) return;
    setLoading(true);
    try {
      const path = filterStr
        ? `/dados/${botKey}/filtered?${filterStr}`
        : `/dados/${botKey}`;
      const d = await apiFetch(path);
      setData(d ?? null);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [botKey, filterStr]);

  useEffect(() => { fetchDados(); }, [fetchDados, refreshTrigger]);

  // Polling fallback only when no active filters (filtered calls are always on-demand)
  useEffect(() => {
    if (filterStr) return;
    const id = setInterval(fetchDados, 60_000);
    return () => clearInterval(id);
  }, [fetchDados, filterStr]);

  const isEmpty = data !== null && typeof data === 'object' && Object.keys(data).length === 0;
  return { data, loading, error, refetch: fetchDados, isEmpty };
}
