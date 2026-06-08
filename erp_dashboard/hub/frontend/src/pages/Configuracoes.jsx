import { useState, useEffect, useRef } from 'react';
import { useMetas } from '../hooks/useMetas';
import { useDados } from '../hooks/useApi';
import { brl } from '../utils/format';

// Parser de número no formato BR: "3.000.000" → 3000000 ; "1.234.567,89" → 1234567.89
function parseBR(str) {
  if (str == null) return 0;
  const cleaned = String(str).replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.');
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? n : 0;
}

export default function Configuracoes() {
  const { metas, loading: metasLoading, salvar } = useMetas();
  const { data: vendas } = useDados('vendas');

  const vendedores = vendas?.top_vendedores ?? [];

  const [totalInput, setTotalInput]   = useState('0');
  const [individuais, setIndividuais] = useState({});
  const [feedback, setFeedback]       = useState(null); // { tipo: 'success'|'error', msg }

  const feedbackTimer = useRef(null);

  useEffect(() => () => { if (feedbackTimer.current) clearTimeout(feedbackTimer.current); }, []);

  useEffect(() => {
    setTotalInput(String(metas.meta_mensal_total || 0));
    setIndividuais({ ...metas.metas_individuais });
  }, [metas]);

  const totalNum  = parseBR(totalInput);
  const mediaVend = vendedores.length > 0 ? totalNum / vendedores.length : 0;

  function distribuir() {
    if (!vendedores.length) return;
    const porVend = Math.round(totalNum / vendedores.length);
    const novo = {};
    for (const v of vendedores) novo[v.Vendedor] = porVend;
    setIndividuais(novo);
  }

  async function handleSalvar() {
    const payload = {
      meta_mensal_total: totalNum,
      metas_individuais: Object.fromEntries(
        Object.entries(individuais).map(([k, v]) => [k, parseBR(v)])
      ),
    };
    const res = await salvar(payload);
    if (res?.ok === true) {
      setFeedback({ tipo: 'success', msg: 'Metas salvas com sucesso!' });
    } else {
      setFeedback({ tipo: 'error', msg: res?.erro || 'Erro ao salvar' });
    }
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => setFeedback(null), 3000);
  }

  if (metasLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando configurações…
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-bold text-text_main">Configurações</h1>

      {/* ── Card 1: Meta Total ─────────────────────────────────────── */}
      <div className="bg-card border border-card_border rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-text_main">Meta Mensal Total</h2>
        <div className="flex items-center gap-3">
          <input
            type="text"
            inputMode="decimal"
            value={totalInput}
            onChange={e => setTotalInput(e.target.value)}
            className="flex-1 bg-bg border border-card_border rounded-lg px-3 py-2 text-text_main text-sm focus:outline-none focus:border-accent"
            placeholder="Ex.: 3.000.000"
          />
          <button
            onClick={distribuir}
            className="bg-accent hover:bg-blue-600 text-white text-xs font-medium px-4 py-2 rounded-lg whitespace-nowrap transition-colors"
          >
            Distribuir igualmente
          </button>
        </div>
        <p className="text-xs text-subtext">
          Meta total:{' '}
          <span className="text-text_main font-medium">{brl(totalNum)}</span>
          {vendedores.length > 0 && (
            <>
              {'  ·  '}Média por vendedor:{' '}
              <span className="text-text_main font-medium">{brl(mediaVend)}</span>
              {' '}({vendedores.length} vendedores)
            </>
          )}
        </p>
      </div>

      {/* ── Card 2: Individual ─────────────────────────────────────── */}
      <div className="bg-card border border-card_border rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-text_main">Meta Individual por Vendedor</h2>

        {vendedores.length === 0 ? (
          <p className="text-xs text-subtext">
            Aguardando dados do bot de vendas… A lista de vendedores aparece após o primeiro ciclo do bot (~10 min).
          </p>
        ) : (
          <div className="space-y-3">
            {vendedores.map(v => (
              <div key={v.Vendedor} className="flex items-center gap-3">
                <span className="flex-1 text-sm text-text_main truncate">{v.Vendedor}</span>
                <input
                  type="text"
                  inputMode="decimal"
                  value={individuais[v.Vendedor] ?? ''}
                  onChange={e => setIndividuais(prev => ({ ...prev, [v.Vendedor]: e.target.value }))}
                  className="w-36 bg-bg border border-card_border rounded-lg px-3 py-1.5 text-text_main text-sm text-right focus:outline-none focus:border-accent"
                  placeholder="0"
                />
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between pt-2 border-t border-card_border">
          {feedback ? (
            <span className={`text-xs font-medium ${feedback.tipo === 'success' ? 'text-success' : 'text-accent_red'}`}>
              {feedback.msg}
            </span>
          ) : (
            <span className="text-xs text-subtext">
              {metas.ultima_atualizacao
                ? `Última atualização: ${new Date(metas.ultima_atualizacao).toLocaleString('pt-BR')}`
                : 'Nenhuma meta salva ainda'}
            </span>
          )}
          <button
            onClick={handleSalvar}
            disabled={vendedores.length === 0}
            className="bg-success hover:bg-green-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-medium px-5 py-2 rounded-lg transition-colors"
          >
            Salvar Metas
          </button>
        </div>
      </div>
    </div>
  );
}
