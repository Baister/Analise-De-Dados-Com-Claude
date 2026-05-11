import { useState, useEffect, useMemo } from 'react';
import { useDados, apiFetch } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import LineChart from '../charts/LineChart';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, pct, shortBrl } from '../utils/format';
import { getUniqueValues, agregaPorDia } from '../utils/filters';

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
  const [meta, setMeta]                     = useState(null);
  const [filtroVendedor, setFiltroVendedor] = useState(null);
  const [filtroMarca, setFiltroMarca]       = useState(null);

  const { data, loading, error, isEmpty } = useDados('dashboard', refreshTrigger);

  useEffect(() => {
    apiFetch('/config').then(d => d && setMeta(d.meta_faturamento_mensal)).catch(() => {});
  }, []);

  const topVendedores = useMemo(() => data?.top_vendedores ?? [], [data]);
  const marcasMes     = useMemo(() => data?.marcas_mes ?? [],     [data]);

  const fatDiario = useMemo(() => {
    if (!data) return [];
    if (filtroVendedor) {
      return agregaPorDia(data.faturamento_diario_por_vendedor ?? [], 'Vendedor', filtroVendedor);
    }
    if (filtroMarca) {
      return agregaPorDia(data.faturamento_diario_por_marca ?? [], 'DescrMarca', filtroMarca);
    }
    return data.faturamento_diario ?? [];
  }, [data, filtroVendedor, filtroMarca]);

  const kpis = useMemo(() => {
    if (!data) return {};
    if (filtroVendedor) {
      const vend = topVendedores.find(v => v.Vendedor === filtroVendedor);
      if (vend) {
        const mb = vend.margem_bruta ?? 0;
        const vb = vend.total_venda  ?? 0;
        return {
          faturamento_atual: vb,
          qtd_documentos:    vend.qtd_pedidos ?? 0,
          ticket_medio:      vend.ticket_medio ?? 0,
          devolucao:         0,
          qtd_devolucoes:    0,
          margem_bruta:      mb,
          pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
        };
      }
    }
    const vb = data.venda_bruta ?? 0;
    const mb = data.margem_bruta ?? 0;
    return {
      faturamento_atual: data.faturamento_atual ?? 0,
      qtd_documentos:    data.qtd_documentos ?? 0,
      ticket_medio:      data.ticket_medio ?? 0,
      devolucao:         data.devolucao ?? 0,
      qtd_devolucoes:    data.qtd_devolucoes ?? 0,
      margem_bruta:      mb,
      pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
    };
  }, [data, filtroVendedor, topVendedores]);

  const vendedoresOpts = useMemo(() => getUniqueValues(topVendedores, 'Vendedor'), [topVendedores]);
  const marcasOpts     = useMemo(() => getUniqueValues(marcasMes, 'DescrMarca'),   [marcasMes]);

  const filterDefs = useMemo(() => [
    { key: 'Vendedor',   label: 'Vendedor', type: 'select', options: vendedoresOpts },
    { key: 'DescrMarca', label: 'Marca',    type: 'select', options: marcasOpts },
  ], [vendedoresOpts, marcasOpts]);

  const filterValues = useMemo(() => ({
    Vendedor:   filtroVendedor ?? 'todos',
    DescrMarca: filtroMarca   ?? 'todos',
  }), [filtroVendedor, filtroMarca]);

  const metaVal = meta ?? data?.meta_mensal ?? 0;
  const pctMeta = metaVal > 0 ? ((kpis.faturamento_atual ?? 0) / metaVal) * 100 : (data?.pct_meta ?? 0);

  function handleFilterChange(newFilters) {
    const newVend  = newFilters.Vendedor   && newFilters.Vendedor   !== 'todos' ? newFilters.Vendedor   : null;
    const newMarca = newFilters.DescrMarca && newFilters.DescrMarca !== 'todos' ? newFilters.DescrMarca : null;
    const vendChanged = newVend !== filtroVendedor;
    if (vendChanged) {
      setFiltroVendedor(newVend);
      setFiltroMarca(newVend ? null : newMarca);
    } else {
      setFiltroMarca(newMarca);
      setFiltroVendedor(null);
    }
  }

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

  const filtroLabel = filtroVendedor
    ? `Vendedor: ${filtroVendedor}`
    : filtroMarca ? `Marca: ${filtroMarca}` : null;

  const fatChartTitle = filtroVendedor
    ? `Faturamento Diário — ${filtroVendedor}`
    : filtroMarca ? `Faturamento Diário — ${filtroMarca}` : 'Faturamento Diário';

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Dashboard</h1>
        <div className="flex items-center gap-3">
          {filtroLabel && (
            <span className="text-xs bg-blue-900/40 text-blue-300 border border-blue-700/40 px-2 py-0.5 rounded">
              {filtroLabel}
            </span>
          )}
          {data?.ultimo_update && (
            <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Faturamento do Mês"
          value={brl(kpis.faturamento_atual ?? 0)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
          sub={metaVal > 0 ? `Meta: ${brl(metaVal)}` : undefined}
        />
        <KpiCard
          label="% da Meta"
          value={pct(pctMeta)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
        />
        <KpiCard label="Ticket Médio" value={brl(kpis.ticket_medio ?? 0)} variant="default" />
        <KpiCard label="Nº Vendas" value={String(kpis.qtd_documentos ?? 0)} variant="default" />
        <KpiCard
          label="Devolução R$"
          value={brl(Math.abs(kpis.devolucao ?? 0))}
          variant={(kpis.devolucao ?? 0) < -5000 ? 'error' : 'default'}
        />
        <KpiCard label="Nº Devoluções" value={String(kpis.qtd_devolucoes ?? 0)} variant="default" />
        <KpiCard
          label="Margem Bruta"
          value={pct(kpis.pct_margem ?? 0)}
          variant={(kpis.pct_margem ?? 0) >= 30 ? 'success' : (kpis.pct_margem ?? 0) >= 15 ? 'warning' : 'error'}
          sub={brl(kpis.margem_bruta ?? 0)}
        />
      </div>

      <FilterBar filters={filterDefs} values={filterValues} onChange={handleFilterChange} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">{fatChartTitle}</h2>
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
            data={topVendedores.slice(0, 10)}
            xKey="Vendedor"
            bars={[{ key: 'total_venda', label: 'Total', formatter: shortBrl }]}
            horizontal
            showLabels
            highlightKey={filtroVendedor}
            height={200}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Faturamento por Marca</h2>
          <PieChart
            data={marcasMes.slice(0, 8)}
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
            data={marcasMes.slice(0, 8)}
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
