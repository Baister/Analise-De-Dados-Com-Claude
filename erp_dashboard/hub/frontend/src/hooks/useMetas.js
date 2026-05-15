import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from './useApi';

const _EMPTY = { meta_mensal_total: 0, metas_individuais: {}, ultima_atualizacao: null };

export function useMetas() {
  const [metas, setMetas]     = useState(_EMPTY);
  const [loading, setLoading] = useState(true);
  const [erro, setErro]       = useState(null);

  const fetchMetas = useCallback(async () => {
    setLoading(true);
    try {
      const d = await apiFetch('/metas');
      if (d) setMetas(d);
      setErro(null);
    } catch (e) {
      setErro(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchMetas(); }, [fetchMetas]);

  const salvar = useCallback(async (payload) => {
    try {
      const res = await apiFetch('/metas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res?.ok) setMetas({ ...payload, ultima_atualizacao: new Date().toISOString() });
      return res ?? { ok: false, erro: 'Sem resposta' };
    } catch (e) {
      return { ok: false, erro: e.message };
    }
  }, []);

  return { metas, loading, erro, salvar, refetch: fetchMetas };
}
