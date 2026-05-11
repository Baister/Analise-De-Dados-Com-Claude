import { useState, useEffect, useCallback } from 'react';

export async function apiFetch(path, opts = {}) {
  const token = localStorage.getItem('erp_token');
  const headers = { ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(path, { ...opts, headers });

  if (res.status === 401) {
    localStorage.removeItem('erp_token');
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
