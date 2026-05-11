import { useState, useEffect } from 'react';
import { useDados, apiFetch } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import LineChart from '../charts/LineChart';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, pct, shortBrl } from '../utils/format';
import { applyFilters, getUniqueValues } from '../utils/filters';

function ProcessingScreen({ label }) {
  return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      <div className="text-center space-y-1">
        <p>{label} está processando dados do banco…</p>
        <p className="text-xs opacity-60">A primeira análise pode levar alguns minutos. A página atualiza automaticamente.</p>
      </div>
    </div>
  );
}

export default function Dashboard({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useDados('dashboard', refreshTrigger);
  const [meta, setMeta] = useState(null);
  const [filters, setFilters] = useState({});

  useEffect(() => {
    apiFetch('/config').then(d => d && setMeta(d.meta_faturamento_mensal)).catch(() => {});
  }, []);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 text-subtext text-sm">
        Carregando dados do dashboard…
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

  if (isEmpty) return <ProcessingScreen label="Bot Dashboard" />;

  const topVendedores = data?.top_vendedores ?? [];
  const fatDiario     = data?.faturamento_diario ?? [];
  const marcasMes     = data?.marcas_mes ?? [];

  const vendedoresOpts = getUniqueValues(topVendedores, 'Vendedor');
  const marcasOpts     = getUniqueValues(marcasMes, 'DescrMarca');

  const filterDefs = [
    { key: 'Vendedor',   label: 'Vendedor', type: 'select', options: vendedoresOpts },
    { key: 'DescrMarca', label: 'Marca',    type: 'select', options: marcasOpts },
  ];

  const filteredVendedores = applyFilters(topVendedores, { Vendedor: filters.Vendedor });
  const filteredMarcas     = applyFilters(marcasMes,     { DescrMarca: filters.DescrMarca });

  const metaVal  = meta ?? data?.meta_mensal ?? 0;
  const fatAtual = data?.faturamento_atual ?? 0;
  const pctMeta  = metaVal > 0 ? (fatAtual / metaVal) * 100 : (data?.pct_meta ?? 0);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Dashboard</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Faturamento do Mês"
          value={brl(fatAtual)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
          sub={metaVal > 0 ? `Meta: ${brl(metaVal)}` : undefined}
        />
        <KpiCard
          label="% da Meta"
          value={pct(pctMeta)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
        />
        <KpiCard label="Documentos" value={String(data?.qtd_documentos ?? 0)} variant="default" />
        <KpiCard label="Ticket Médio" value={brl(data?.ticket_medio ?? 0)} variant="default" />
      </div>

      <FilterBar filters={filterDefs} values={filters} onChange={setFilters} />

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Faturamento Diário</h2>
          <LineChart
            data={fatDiario}
            xKey="dia"
            lines={[{ key: 'faturamento', label: 'Faturamento', formatter: shortBrl }]}
            height={200}
          />
        </div>

        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Top Vendedores</h2>
          <BarChart
            data={filteredVendedores.slice(0, 10)}
            xKey="Vendedor"
            bars={[{ key: 'total_venda', label: 'Total', formatter: shortBrl }]}
            horizontal
            showLabels
            height={200}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Faturamento por Marca</h2>
          <PieChart
            data={filteredMarcas.slice(0, 8)}
            nameKey="DescrMarca"
            valueKey="faturamento"
            showValue
            formatter={shortBrl}
            height={220}
          />
        </div>
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Itens Vendidos por Marca</h2>
          <PieChart
            data={filteredMarcas.slice(0, 8)}
            nameKey="DescrMarca"
            valueKey="quantidade"
            showValue
            height={220}
          />
        </div>
      </div>
    </div>
  );
}
