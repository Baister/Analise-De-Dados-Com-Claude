import { useState, useMemo } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import DataTable from '../components/DataTable';
import { brl, shortBrl, fmtDate } from '../utils/format';
import { applyFilters, getUniqueValues } from '../utils/filters';
import { classifyABC } from '../utils/estoque';

const STATUS_COLS = [
  { key: 'status',    label: 'Status' },
  { key: 'quantidade', label: 'Qtd', render: v => String(v ?? 0) },
];

const CURVA_AB_COLS = [
  { key: 'CodItem',         label: 'Código' },
  { key: 'DescrItem',       label: 'Descrição' },
  { key: 'DescrMarca',      label: 'Marca' },
  { key: 'QtdEstq',         label: 'Qtd Estq',    render: v => String(v ?? 0) },
  { key: 'giro90d',         label: 'Giro 90d',     render: v => (v ?? 0).toFixed(2) },
  { key: 'val_vendido_90d', label: 'Vlr Vend 90d', render: v => shortBrl(v) },
];

const CURVA_C_COLS = [
  { key: 'CodItem',    label: 'Código' },
  { key: 'DescrItem',  label: 'Descrição' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'QtdEstq',    label: 'Qtd Estq',      render: v => String(v ?? 0) },
  { key: 'giro90d',    label: 'Giro 90d',       render: v => (v ?? 0).toFixed(2) },
  { key: 'DtUltVnd',   label: 'Sem giro desde', render: v => (v ? fmtDate(v) : '—') },
];

const ZERADOS_COLS = [
  { key: 'CodItem',    label: 'Código' },
  { key: 'DescrItem',  label: 'Descrição' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'VlrEstq',    label: 'Vlr Estq',     render: v => brl(v) },
  { key: 'DtUltVnd',   label: 'Zerado desde', render: v => (v ? fmtDate(v) : '—') },
];

function textFilter(list, query) {
  const q = query.trim().toLowerCase();
  if (!q) return list;
  return list.filter(r =>
    (r.DescrItem ?? '').toLowerCase().includes(q) ||
    String(r.CodItem ?? '').toLowerCase().includes(q)
  );
}

function TextInput({ value, onChange }) {
  return (
    <input
      type="text"
      placeholder="Filtrar por produto ou código..."
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full px-3 py-1.5 text-xs bg-card_border border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-blue-500 mb-3"
    />
  );
}

export default function Estoque({ refreshTrigger }) {
  const [filters, setFilters]           = useState({});
  const [textoA, setTextoA]             = useState('');
  const [textoB, setTextoB]             = useState('');
  const [textoC, setTextoC]             = useState('');
  const [textoZerados, setTextoZerados] = useState('');

  const apiFilters = useMemo(() => {
    const f = {};
    if (filters.DescrMarca && filters.DescrMarca !== 'todos') f.marca = filters.DescrMarca;
    return f;
  }, [filters]);

  const { data, loading, error, isEmpty } = useFilteredDados('estoque', apiFilters, refreshTrigger);

  const porMarca    = data?.por_marca    ?? [];
  const giroBruto   = data?.giro_bruto   ?? [];
  const zeradosLista = data?.zerados_lista ?? [];

  const marcasOpts = getUniqueValues(porMarca, 'DescrMarca');

  const filterDefs = [
    { key: 'DescrMarca', label: 'Marca', type: 'select', options: marcasOpts },
  ];

  const filteredMarcas = applyFilters(porMarca, { DescrMarca: filters.DescrMarca });

  // Classificação ABC — roda uma vez, gera três curvas
  const classified = useMemo(() => {
    const c = classifyABC(giroBruto);
    return c.map(r => ({ ...r, giro90d: r.qtd_vendida_90d / Math.max(r.QtdEstq ?? 1, 1) }));
  }, [giroBruto]);

  const curvaALista = useMemo(() => classified.filter(r => r.abc === 'A'), [classified]);
  const curvaBLista = useMemo(() => classified.filter(r => r.abc === 'B'), [classified]);
  const curvaCLista = useMemo(() => classified.filter(r => r.abc === 'C'), [classified]);

  const curvaAFiltrado  = useMemo(() => textFilter(curvaALista,  textoA),       [curvaALista,  textoA]);
  const curvaBFiltrado  = useMemo(() => textFilter(curvaBLista,  textoB),       [curvaBLista,  textoB]);
  const curvaCFiltrado  = useMemo(() => textFilter(curvaCLista,  textoC),       [curvaCLista,  textoC]);
  const zeradosFiltrado = useMemo(() => textFilter(zeradosLista, textoZerados), [zeradosLista, textoZerados]);

  const totalItens   = data?.total_itens   ?? 0;
  const itensZerados = data?.itens_zerados ?? 0;
  const itensSemGiro = data?.itens_sem_giro ?? 0;

  const statusData = [
    { status: 'Normal',   quantidade: totalItens - itensZerados - itensSemGiro },
    { status: 'Zerados',  quantidade: itensZerados },
    { status: 'Sem Giro', quantidade: itensSemGiro },
  ].filter(r => r.quantidade > 0);

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
          <p className="text-xs opacity-60">O Estoque tem muitos dados e pode levar alguns minutos. A página atualiza automaticamente.</p>
        </div>
      </div>
    );
  }

  const loadingABC = !data || !('giro_bruto' in data);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Estoque</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total de Itens"   value={String(totalItens)}                          variant="default" />
        <KpiCard label="Valor em Estoque" value={brl(data?.valor_total_estoque ?? 0)}         variant="default" />
        <KpiCard label="Itens Zerados"    value={String(itensZerados)}
          variant={itensZerados > 0 ? 'warning' : 'success'} />
        <KpiCard label="Sem Giro"         value={String(itensSemGiro)}
          variant={itensSemGiro > 0 ? 'warning' : 'success'} />
      </div>

      <FilterBar filters={filterDefs} values={filters} onChange={setFilters} />

      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Valor por Marca</h2>
          <BarChart
            data={filteredMarcas.slice(0, 10)}
            xKey="DescrMarca"
            bars={[{ key: 'valor_estoque', label: 'Valor', formatter: shortBrl }]}
            horizontal
            showLabels
            height={220}
          />
        </div>
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Status do Estoque</h2>
          <PieChart
            data={statusData}
            nameKey="status"
            valueKey="quantidade"
            showValue={false}
            height={220}
          />
        </div>
      </div>

      {/* Curva A + Curva B */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-2">
            Curva A — Alto Giro ({loadingABC ? '…' : curvaAFiltrado.length})
          </h2>
          <TextInput value={textoA} onChange={setTextoA} />
          {loadingABC
            ? <p className="text-xs text-subtext">Carregando análise de giro…</p>
            : <DataTable columns={CURVA_AB_COLS} rows={curvaAFiltrado} />}
        </div>
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-2">
            Curva B — Giro Médio ({loadingABC ? '…' : curvaBFiltrado.length})
          </h2>
          <TextInput value={textoB} onChange={setTextoB} />
          {loadingABC
            ? <p className="text-xs text-subtext">Carregando análise de giro…</p>
            : <DataTable columns={CURVA_AB_COLS} rows={curvaBFiltrado} />}
        </div>
      </div>

      {/* Curva C + Zerados */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-2">
            Curva C — Sem Giro ({loadingABC ? '…' : curvaCFiltrado.length})
          </h2>
          <TextInput value={textoC} onChange={setTextoC} />
          {loadingABC
            ? <p className="text-xs text-subtext">Carregando análise de giro…</p>
            : <DataTable columns={CURVA_C_COLS} rows={curvaCFiltrado} />}
        </div>
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-2">
            Itens Zerados ({zeradosFiltrado.length})
          </h2>
          <TextInput value={textoZerados} onChange={setTextoZerados} />
          <DataTable columns={ZERADOS_COLS} rows={zeradosFiltrado} />
        </div>
      </div>
    </div>
  );
}
