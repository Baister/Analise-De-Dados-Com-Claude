import { useState } from 'react';
import { useDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import PieChart from '../charts/PieChart';
import BarChart from '../charts/BarChart';
import DataTable from '../components/DataTable';
import { brl, pct, fmtDate } from '../utils/format';
import { applyFilters, getUniqueValues } from '../utils/filters';

const INAT_COLS = [
  { key: 'CodCli', label: 'Cód.' },
  { key: 'NomeCli', label: 'Cliente' },
  { key: 'UltVenda', label: 'Última Venda', render: v => (v ? fmtDate(v) : '—') },
  { key: 'DiasInativo', label: 'Dias Inativo', render: v => String(v ?? 0) },
  { key: 'VlrUltVenda', label: 'Vlr Última Venda', render: v => brl(v) },
];

export default function CRM({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useDados('crm', refreshTrigger);
  const [filters, setFilters] = useState({});

  const convPorVendedor = data?.conv_por_vendedor ?? [];
  const inativos = data?.inativos_lista ?? [];
  const statusFunil = data?.funil_status ?? [];

  const vendedoresOpts = getUniqueValues(convPorVendedor, 'Vendedor');

  const filterDefs = [
    { key: 'Vendedor', label: 'Vendedor', type: 'select', options: vendedoresOpts },
  ];

  const filteredConv = applyFilters(convPorVendedor, { Vendedor: filters.Vendedor });

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando dados de CRM…
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
          <p>Bot CRM está processando dados do banco…</p>
          <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">CRM</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Orçamentos no Mês" value={String(data?.qtd_orcamentos ?? 0)} variant="default" />
        <KpiCard
          label="Taxa de Conversão"
          value={pct(data?.taxa_conversao ?? 0)}
          variant={(data?.taxa_conversao ?? 0) >= 40 ? 'success' : 'warning'}
        />
        <KpiCard label="Clientes Inativos" value={String(data?.qtd_inativos ?? 0)} variant="warning" />
        <KpiCard label="Orçamentos Abertos" value={String(data?.qtd_abertos ?? 0)} variant="default" />
      </div>

      <FilterBar filters={filterDefs} values={filters} onChange={setFilters} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Status funil */}
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Funil de Vendas</h2>
          <PieChart
            data={statusFunil.slice(0, 6)}
            nameKey="status"
            valueKey="quantidade"
            showValue={false}
            height={220}
          />
        </div>

        {/* Conversão por vendedor */}
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Conversão por Vendedor</h2>
          <BarChart
            data={filteredConv.slice(0, 10)}
            xKey="Vendedor"
            bars={[
              { key: 'qtd_orcamentos', label: 'Orçamentos' },
              { key: 'qtd_convertidos', label: 'Convertidos' },
            ]}
            stacked={false}
            height={220}
          />
        </div>
      </div>

      {/* Clientes inativos */}
      <div className="bg-card border border-card_border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-text_main mb-3">
          Clientes Inativos ({inativos.length})
        </h2>
        <DataTable columns={INAT_COLS} rows={inativos} />
      </div>
    </div>
  );
}
