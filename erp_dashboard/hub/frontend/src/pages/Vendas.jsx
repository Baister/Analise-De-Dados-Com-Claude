import { useState } from 'react';
import { useDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, pct, shortBrl } from '../utils/format';
import { applyFilters, getUniqueValues } from '../utils/filters';

export default function Vendas({ refreshTrigger }) {
  const { data, loading, error } = useDados('vendas', refreshTrigger);
  const [filters, setFilters] = useState({});

  const topVendedores = data?.top_vendedores ?? [];
  const marcas = data?.marcas_mes ?? [];
  const ticketMedio = data?.ticket_medio_vendedor ?? [];

  const vendedoresOpts = getUniqueValues(topVendedores, 'Vendedor');
  const marcasOpts = getUniqueValues(marcas, 'DescrMarca');

  const filterDefs = [
    { key: 'Vendedor', label: 'Vendedor', type: 'select', options: vendedoresOpts },
    { key: 'DescrMarca', label: 'Marca', type: 'select', options: marcasOpts },
  ];

  const filteredVendedores = applyFilters(topVendedores, { Vendedor: filters.Vendedor });
  const filteredMarcas = applyFilters(marcas, { DescrMarca: filters.DescrMarca });
  const filteredTicket = applyFilters(ticketMedio, { Vendedor: filters.Vendedor });

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando dados de vendas…
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

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Vendas</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Faturamento do Mês" value={brl(data?.faturamento_atual ?? 0)} variant="default" />
        <KpiCard label="Qtd Documentos" value={String(data?.qtd_documentos ?? 0)} variant="default" />
        <KpiCard label="Ticket Médio" value={brl(data?.ticket_medio ?? 0)} variant="default" />
        <KpiCard label="Clientes Ativos" value={String(data?.clientes_ativos ?? 0)} variant="default" />
      </div>

      <FilterBar filters={filterDefs} values={filters} onChange={setFilters} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Vendedores */}
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Top Vendedores</h2>
          <BarChart
            data={filteredVendedores.slice(0, 10)}
            xKey="Vendedor"
            bars={[{ key: 'total_venda', label: 'Total', formatter: shortBrl }]}
            horizontal
            showLabels
            height={220}
          />
        </div>

        {/* Marcas */}
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Faturamento por Marca</h2>
          <PieChart
            data={filteredMarcas.slice(0, 6)}
            nameKey="DescrMarca"
            valueKey="faturamento"
            showValue
            formatter={shortBrl}
            height={220}
          />
        </div>
      </div>

      {/* Ticket médio por vendedor */}
      {filteredTicket.length > 0 && (
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Ticket Médio por Vendedor</h2>
          <BarChart
            data={filteredTicket.slice(0, 10)}
            xKey="Vendedor"
            bars={[{ key: 'ticket_medio', label: 'Ticket Médio', formatter: shortBrl }]}
            horizontal
            showLabels
            height={220}
          />
        </div>
      )}
    </div>
  );
}
