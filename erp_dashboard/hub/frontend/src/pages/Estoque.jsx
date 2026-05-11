import { useState, useMemo } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import DataTable from '../components/DataTable';
import { brl, shortBrl, fmtDate } from '../utils/format';
import { applyFilters, applyDateFilter, getUniqueValues } from '../utils/filters';

const STATUS_COLS = [
  { key: 'status', label: 'Status' },
  { key: 'quantidade', label: 'Qtd', render: v => String(v ?? 0) },
];

const CRITICOS_COLS = [
  { key: 'CodItem', label: 'Código' },
  { key: 'DescrItem', label: 'Descrição' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'QtdEstq', label: 'Qtd Estq', render: v => String(v ?? 0) },
  { key: 'QtdEstqDisp', label: 'Disponível', render: v => String(v ?? 0) },
  { key: 'VlrEstq', label: 'Valor', render: v => brl(v) },
  { key: 'DtUltVnd', label: 'Últ. Venda', render: v => (v ? fmtDate(v) : '—') },
];

export default function Estoque({ refreshTrigger }) {
  const [filters, setFilters] = useState({});
  const apiFilters = useMemo(() => {
    const f = {};
    if (filters.DescrMarca && filters.DescrMarca !== 'todos') f.marca  = filters.DescrMarca;
    if (filters.dtUltVnd_de)   f.dt_de  = filters.dtUltVnd_de;
    if (filters.dtUltVnd_ate)  f.dt_ate = filters.dtUltVnd_ate;
    return f;
  }, [filters]);
  const { data, loading, error, isEmpty } = useFilteredDados('estoque', apiFilters, refreshTrigger);

  const criticos = data?.criticos ?? [];
  const porMarca = data?.por_marca ?? [];

  const marcasOpts = getUniqueValues(porMarca, 'DescrMarca');

  const filterDefs = [
    { key: 'DescrMarca', label: 'Marca', type: 'select', options: marcasOpts },
    { key: 'dtUltVnd', label: 'Últ. Venda', type: 'daterange' },
  ];

  const filteredMarcas = applyFilters(porMarca, { DescrMarca: filters.DescrMarca });
  let filteredCriticos = applyFilters(criticos, { DescrMarca: filters.DescrMarca });
  filteredCriticos = applyDateFilter(
    filteredCriticos,
    'DtUltVnd',
    filters.dtUltVnd_de,
    filters.dtUltVnd_ate,
  );

  const totalItens = data?.total_itens ?? 0;
  const itensZerados = data?.itens_zerados ?? 0;
  const itensSemGiro = data?.itens_sem_giro ?? 0;

  const statusData = [
    { status: 'Normal', quantidade: totalItens - itensZerados - itensSemGiro },
    { status: 'Zerados', quantidade: itensZerados },
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
        <KpiCard label="Total de Itens" value={String(totalItens)} variant="default" />
        <KpiCard label="Valor em Estoque" value={brl(data?.valor_total_estoque ?? 0)} variant="default" />
        <KpiCard
          label="Itens Zerados"
          value={String(itensZerados)}
          variant={itensZerados > 0 ? 'warning' : 'success'}
        />
        <KpiCard
          label="Sem Giro"
          value={String(itensSemGiro)}
          variant={itensSemGiro > 0 ? 'warning' : 'success'}
        />
      </div>

      <FilterBar filters={filterDefs} values={filters} onChange={setFilters} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Por marca */}
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

        {/* Status */}
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

      {/* Itens críticos */}
      <div className="bg-card border border-card_border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-text_main mb-3">
          Itens Críticos ({filteredCriticos.length})
        </h2>
        <DataTable columns={CRITICOS_COLS} rows={filteredCriticos} />
      </div>
    </div>
  );
}
