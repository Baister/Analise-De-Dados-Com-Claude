import { useState, useMemo } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import { brl, shortBrl, fmtDate } from '../utils/format';
import { getUniqueValues } from '../utils/filters';
import { classifyABC } from '../utils/estoque';

const PAGE_SIZE = 50;

// ─── Column definitions ────────────────────────────────────────────────────
const CURVA_AB_COLS = [
  { key: 'CodItem',         label: 'Código' },
  { key: 'DescrItem',       label: 'Descrição' },
  { key: 'DescrMarca',      label: 'Marca' },
  { key: 'QtdEstq',         label: 'Qtd',       render: v => String(v ?? 0) },
  { key: 'giro90d',         label: 'Giro 90d',  render: v => (v ?? 0).toFixed(2) },
  { key: 'val_vendido_90d', label: 'Vlr 90d',   render: v => shortBrl(v) },
];

const CURVA_C_COLS = [
  { key: 'CodItem',    label: 'Código' },
  { key: 'DescrItem',  label: 'Descrição' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'QtdEstq',    label: 'Qtd',          render: v => String(v ?? 0) },
  { key: 'giro90d',    label: 'Giro 90d',     render: v => (v ?? 0).toFixed(2) },
  { key: 'DtUltVnd',   label: 'Última venda', render: v => (v ? fmtDate(v) : '—') },
];

const ZERADOS_COLS = [
  { key: 'CodItem',    label: 'Código' },
  { key: 'DescrItem',  label: 'Descrição' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'VlrEstq',    label: 'Vlr Estq',    render: v => brl(v) },
  { key: 'DtUltVnd',   label: 'Zerado desde', render: v => (v ? fmtDate(v) : '—') },
];

function fmtTempo(dias) {
  if (dias == null) return 'Nunca vendido';
  if (dias >= 365) {
    const a = Math.floor(dias / 365);
    const m = Math.floor((dias % 365) / 30);
    return m > 0 ? `${a}a ${m}m` : `${a} ano${a !== 1 ? 's' : ''}`;
  }
  if (dias >= 30) return `${Math.floor(dias / 30)} meses`;
  return `${dias} dias`;
}

const SEM_GIRO_COLS = [
  { key: 'CodItem',        label: 'Código' },
  { key: 'DescrItem',      label: 'Descrição' },
  { key: 'DescrMarca',     label: 'Marca' },
  { key: 'QtdEstq',        label: 'Qtd',          render: v => String(v ?? 0) },
  { key: 'VlrEstq',        label: 'Vlr Estq',     render: v => shortBrl(v) },
  { key: 'DiasSemVndReal', label: 'Tempo parado', render: v => fmtTempo(v) },
  { key: 'DtUltVnd',       label: 'Última venda', render: v => (v ? fmtDate(v) : '—') },
];

// Maps activeCurva key → column definition for DataTable
const COLS_ABC = { A: CURVA_AB_COLS, B: CURVA_AB_COLS, C: CURVA_C_COLS, Z: ZERADOS_COLS, S: SEM_GIRO_COLS };

// ─── ABC curve metadata ────────────────────────────────────────────────────
const CURVAS = [
  { key: 'A', label: 'Curva A',  sub: 'Alto Giro',  color: '#238636' },
  { key: 'B', label: 'Curva B',  sub: 'Giro Médio', color: '#d29922' },
  { key: 'C', label: 'Curva C',  sub: 'Baixo Giro', color: '#da3633' },
  { key: 'Z', label: 'Zerados',  sub: 'Estq = 0',   color: '#8b949e' },
  { key: 'S', label: 'Sem Giro', sub: '90+ dias',   color: '#a371f7' },
];

// ─── Helpers ───────────────────────────────────────────────────────────────
function textFilter(list, query) {
  const q = query.trim().toLowerCase();
  if (!q) return list;
  return list.filter(r =>
    (r.DescrItem ?? '').toLowerCase().includes(q) ||
    String(r.CodItem ?? '').toLowerCase().includes(q)
  );
}

// ─── Component ────────────────────────────────────────────────────────────
export default function Estoque({ refreshTrigger }) {
  const [filters, setFilters]         = useState({});
  const [activeCurva, setActiveCurva] = useState('A');
  const [textoBusca, setTextoBusca]   = useState('');
  const [curvaPage, setCurvaPage]     = useState(0);

  const apiFilters = useMemo(() => {
    const f = {};
    if (filters.DescrMarca && filters.DescrMarca !== 'todos') f.marca = filters.DescrMarca;
    return f;
  }, [filters]);

  const { data, loading, error, isEmpty } = useFilteredDados('estoque', apiFilters, refreshTrigger);

  // ── Raw data from API ──
  const porMarca     = data?.por_marca     ?? [];
  const giroBruto    = data?.giro_bruto    ?? [];
  const zeradosLista = data?.zerados_lista ?? [];
  const semGiroLista = data?.sem_giro_lista ?? [];
  const totalItens   = data?.total_itens   ?? 0;
  const itensZerados = data?.itens_zerados ?? 0;
  const itensSemGiro = data?.itens_sem_giro ?? 0;

  // Marca options for the header dropdown
  const marcasOpts = getUniqueValues(porMarca, 'DescrMarca');

  // ── ABC classification (runs once per giroBruto change) ──
  const classified = useMemo(() => {
    const c = classifyABC(giroBruto);
    return c.map(r => ({ ...r, giro90d: r.qtd_vendida_90d / Math.max(r.QtdEstq ?? 1, 1) }));
  }, [giroBruto]);

  const curvaALista = useMemo(() => classified.filter(r => r.abc === 'A'), [classified]);
  const curvaBLista = useMemo(() => classified.filter(r => r.abc === 'B'), [classified]);
  const curvaCLista = useMemo(() => classified.filter(r => r.abc === 'C'), [classified]);

  // Active curve rows + text filter applied
  const curvaRows = useMemo(() => {
    if (activeCurva === 'A') return curvaALista;
    if (activeCurva === 'B') return curvaBLista;
    if (activeCurva === 'C') return curvaCLista;
    if (activeCurva === 'S') return semGiroLista;
    return zeradosLista;
  }, [activeCurva, curvaALista, curvaBLista, curvaCLista, zeradosLista, semGiroLista]);

  const curvaRowsFiltrado = useMemo(
    () => textFilter(curvaRows, textoBusca),
    [curvaRows, textoBusca]
  );

  // Pagination
  const totalPages = Math.ceil(curvaRowsFiltrado.length / PAGE_SIZE);
  const curvaRowsPage = useMemo(
    () => curvaRowsFiltrado.slice(curvaPage * PAGE_SIZE, (curvaPage + 1) * PAGE_SIZE),
    [curvaRowsFiltrado, curvaPage]
  );

  // Count per curve key (for mini-card labels)
  const curvaCounts = useMemo(() => ({
    A: curvaALista.length,
    B: curvaBLista.length,
    C: curvaCLista.length,
    Z: zeradosLista.length,
    S: semGiroLista.length,
  }), [curvaALista, curvaBLista, curvaCLista, zeradosLista, semGiroLista]);

  // True while giro_bruto hasn't arrived yet (analisar() is still running)
  const loadingABC = !data || !('giro_bruto' in data);

  // ── Helper to change curva and reset page + search ──
  function selectCurva(key) {
    setActiveCurva(key);
    setTextoBusca('');
    setCurvaPage(0);
  }

  // ── Early returns ──
  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando dados de estoque…
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-accent_red text-sm">
        Erro ao carregar dados: {error}
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        <div className="text-center space-y-1">
          <p>Bot Estoque está processando dados do banco…</p>
          <p className="text-xs opacity-60">
            O Estoque tem muitos dados e pode levar alguns minutos. A página atualiza automaticamente.
          </p>
        </div>
      </div>
    );
  }

  const curvaAtiva = CURVAS.find(c => c.key === activeCurva) ?? CURVAS[0];

  return (
    <div className="p-6">

      {/* ── Header row ── */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-text_main">Estoque</h1>
        <div className="flex items-center gap-3">
          <select
            value={filters.DescrMarca || 'todos'}
            onChange={e => { setFilters({ ...filters, DescrMarca: e.target.value }); setTextoBusca(''); setActiveCurva('A'); setCurvaPage(0); }}
            className="bg-card border border-card_border rounded-lg px-3 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent"
          >
            {marcasOpts.map(opt => (
              <option key={opt} value={opt}>
                {opt === 'todos' ? 'Todas as marcas' : opt}
              </option>
            ))}
          </select>
          {data?.ultimo_update && (
            <span className="text-subtext text-xs">Atualizado {data.ultimo_update}</span>
          )}
        </div>
      </div>

      {/* ── Two-column body ── */}
      <div className="flex gap-3 items-start">

        {/* ── Left column (35%) ── */}
        <div className="w-[35%] flex flex-col gap-3">

          {/* KPI 2×2 grid */}
          <div className="grid grid-cols-2 gap-2">
            <KpiCard
              label="Total de Itens"
              value={String(totalItens)}
              topBorder="#1f6feb"
            />
            <KpiCard
              label="Valor em Estoque"
              value={shortBrl(data?.valor_total_estoque ?? 0)}
              topBorder="#1f6feb"
            />
            <KpiCard
              label="Itens Zerados"
              value={String(itensZerados)}
              topBorder="#da3633"
              variant={itensZerados > 0 ? 'error' : 'default'}
            />
            <KpiCard
              label="Sem Giro"
              value={String(itensSemGiro)}
              topBorder="#d29922"
              variant={itensSemGiro > 0 ? 'warning' : 'default'}
            />
          </div>

          {/* Brand ranking list */}
          <div className="bg-card border border-card_border rounded-lg p-3">
            <p className="text-[10px] font-semibold text-subtext uppercase tracking-wider mb-2">
              Valor por Marca
            </p>
            <div className="flex flex-col gap-1.5">
              {porMarca.slice(0, 5).map((m, i) => (
                <div
                  key={m.DescrMarca}
                  className="flex justify-between items-center px-2 py-1.5 bg-progress_bg rounded text-xs"
                  style={{ borderLeft: `3px solid rgba(31,111,235,${(1 - i * 0.18).toFixed(2)})` }}
                >
                  <span className="text-text_main font-medium truncate">{m.DescrMarca}</span>
                  <span className="text-subtext ml-2 shrink-0">{shortBrl(m.valor_estoque)}</span>
                </div>
              ))}
              {porMarca.length > 5 && (
                <div className="flex justify-between items-center px-2 py-1.5 text-xs">
                  <span className="text-subtext">+ {porMarca.length - 5} marcas</span>
                  <span className="text-subtext">
                    {shortBrl(porMarca.slice(5).reduce((s, m) => s + (Number(m.valor_estoque) || 0), 0))}
                  </span>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* ── Right column — ABC block ── */}
        <div className="flex-1 bg-card border border-card_border rounded-lg p-4">

          {/* Section header with divider */}
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Análise ABC
            </span>
            <div className="flex-1 h-px bg-card_border" />
            <span className="text-[9px] text-subtext">últimos 90 dias</span>
          </div>

          {/* Mini-card selector — 5 colunas */}
          <div className="grid grid-cols-5 gap-1.5 mb-3">
            {CURVAS.map(c => {
              const active = activeCurva === c.key;
              // Sem Giro usa semGiroLista.length diretamente (disponível antes do giro_bruto)
              const count = c.key === 'S'
                ? semGiroLista.length
                : (loadingABC ? null : curvaCounts[c.key]);
              return (
                <button
                  key={c.key}
                  onClick={() => selectCurva(c.key)}
                  className="rounded-lg p-2 text-center transition-all"
                  style={
                    active
                      ? { background: c.color, boxShadow: `0 0 0 2px ${c.color}66` }
                      : { background: '#21262d', border: `1px solid ${c.color}` }
                  }
                >
                  <div className="text-base font-bold leading-tight" style={{ color: active ? '#fff' : c.color }}>
                    {count === null ? '…' : count}
                  </div>
                  <div className="text-[9px] mt-0.5 truncate" style={{ color: active ? '#ffffff99' : '#8b949e' }}>
                    {c.label}
                  </div>
                  <div className="text-[8px]" style={{ color: active ? '#ffffff77' : '#8b949e' }}>
                    {c.sub}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Active curve label + text filter */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold" style={{ color: curvaAtiva.color }}>
              ▼ {curvaAtiva.label} — {curvaAtiva.sub}
            </span>
            <div className="flex-1" />
            <div className="w-48">
              <input
                type="text"
                placeholder="Filtrar por produto ou código..."
                value={textoBusca}
                onChange={e => { setTextoBusca(e.target.value); setCurvaPage(0); }}
                className="w-full px-3 py-1.5 text-xs bg-card_border border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* Detail table */}
          {loadingABC && activeCurva !== 'S' && activeCurva !== 'Z'
            ? <p className="text-xs text-subtext py-4">Carregando análise de giro…</p>
            : <DataTable columns={COLS_ABC[activeCurva]} rows={curvaRowsPage} />
          }

          {/* Pagination controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-2 text-[10px] text-subtext">
              <span>{curvaRowsFiltrado.length} itens · pág {curvaPage + 1}/{totalPages}</span>
              <div className="flex items-center gap-1">
                <button
                  disabled={curvaPage === 0}
                  onClick={() => setCurvaPage(0)}
                  className="px-1.5 py-0.5 rounded bg-card_border disabled:opacity-30 hover:text-text_main"
                >«</button>
                <button
                  disabled={curvaPage === 0}
                  onClick={() => setCurvaPage(p => p - 1)}
                  className="px-1.5 py-0.5 rounded bg-card_border disabled:opacity-30 hover:text-text_main"
                >‹</button>
                <button
                  disabled={curvaPage >= totalPages - 1}
                  onClick={() => setCurvaPage(p => p + 1)}
                  className="px-1.5 py-0.5 rounded bg-card_border disabled:opacity-30 hover:text-text_main"
                >›</button>
                <button
                  disabled={curvaPage >= totalPages - 1}
                  onClick={() => setCurvaPage(totalPages - 1)}
                  className="px-1.5 py-0.5 rounded bg-card_border disabled:opacity-30 hover:text-text_main"
                >»</button>
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
