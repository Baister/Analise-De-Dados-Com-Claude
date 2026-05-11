import { useState, useEffect, useCallback } from 'react';

export async function apiFetch(path, opts = {}) {
  const token = localStorage.getItem('erp_token');
  const headers = { ...opts.headers };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(path, { ...opts, headers });

  if (res.status === 401) {
    localStorage.removeItem('erp_token');
    location.reload();
    return;
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

// useDados: hook para páginas que consomem um único bot.
// refreshTrigger: qualquer valor — mudança dispara refetch.
export function useDados(botKey, refreshTrigger) {
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDados = useCallback(async () => {
    if (!botKey) return;
    setLoading(true);
    try {
      const d = await apiFetch(`/dados/${botKey}`);
      setDados(d);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [botKey]);

  useEffect(() => { fetchDados(); }, [fetchDados, refreshTrigger]);

  return { dados, loading, error, refetch: fetchDados };
}
