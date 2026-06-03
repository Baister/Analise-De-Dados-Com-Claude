import { useState, useEffect, useMemo } from 'react';
import { useDados, apiFetch } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import LineChart from '../charts/LineChart';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, pct, shortBrl } from '../utils/format';
import { getUniqueValues, agregaPorDia } from '../utils/filters';
import { countBusinessDaysSP } from '../utils/businessDays';

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
  const topItens      = useMemo(() => (data?.top_itens_mes ?? []).slice(0, 8), [data]);

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
          qtd_documentos:    vend.qtd_pedidos    ?? 0,
          qtd_vendas_bruta:  vend.qtd_pedidos    ?? 0,
          qtd_vendas_dev:    vend.qtd_devolucoes ?? 0,
          ticket_medio:      vend.ticket_medio   ?? 0,
          devolucao:         vend.devolucao      ?? 0,
          qtd_devolucoes:    vend.qtd_devolucoes ?? 0,
          margem_bruta:      mb,
          pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
        };
      }
    }
    if (filtroMarca) {
      const marca = marcasMes.find(m => m.DescrMarca === filtroMarca);
      if (marca) {
        const vlp = marca.venda_liq_prod ?? 0;
        const lp  = marca.lucro_prod     ?? 0;
        return {
          faturamento_atual: vlp,
          qtd_documentos:    marca.quantidade  ?? 0,
          qtd_vendas_bruta:  0,
          qtd_vendas_dev:    0,
          ticket_medio:      0,
          devolucao:         0,
          qtd_devolucoes:    0,
          margem_bruta:      lp,
          pct_margem:        vlp > 0 ? (lp / vlp) * 100 : 0,
        };
      }
    }
    const vb = data.venda_bruta ?? 0;
    const mb = data.margem_bruta ?? 0;
    return {
      faturamento_atual: data.faturamento_atual ?? 0,
      qtd_documentos:    data.qtd_documentos ?? 0,
      qtd_vendas_bruta:  data.qtd_vendas_bruta ?? 0,
      qtd_vendas_dev:    data.qtd_vendas_dev   ?? 0,
      ticket_medio:      data.ticket_medio ?? 0,
      devolucao:         data.devolucao ?? 0,
      qtd_devolucoes:    data.qtd_devolucoes ?? 0,
      margem_bruta:      mb,
      pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
    };
  }, [data, filtroVendedor, filtroMarca, topVendedores, marcasMes]);

  const vendedoresOpts   = useMemo(() => getUniqueValues(topVendedores, 'Vendedor'), [topVendedores]);
  const marcasOpts       = useMemo(() => getUniqueValues(marcasMes, 'DescrMarca'),   [marcasMes]);
  const topVendedoresFiltrados = useMemo(() => {
    if (filtroMarca && data?.marcas_por_vendedor?.length) {
      return data.marcas_por_vendedor
        .filter(m => m.DescrMarca === filtroMarca)
        .sort((a, b) => (b.venda_liq_prod ?? 0) - (a.venda_liq_prod ?? 0))
        .slice(0, 10);
    }
    return topVendedores.slice(0, 10);
  }, [data, filtroMarca, topVendedores]);

  const vendYAxisWidth   = useMemo(() => {
    const src = filtroMarca ? topVendedoresFiltrados : topVendedores;
    const longest = src.reduce((max, v) => Math.max(max, (v.Vendedor ?? '').length), 0);
    return Math.min(160, Math.max(90, longest * 7));
  }, [filtroMarca, topVendedoresFiltrados, topVendedores]);

  const metaVal = meta ?? data?.meta_mensal ?? 0;

  const metaDiaria = useMemo(() => {
    if (!metaVal) return 0;
    const now = new Date();
    return metaVal / countBusinessDaysSP(now.getFullYear(), now.getMonth() + 1);
  }, [metaVal]);

  const fatHoje = useMemo(() => {
    const hoje = new Date().toISOString().slice(0, 10);
    const entry = (data?.faturamento_diario ?? []).find(r => String(r.dia).slice(0, 10) === hoje);
    return entry?.faturamento ?? 0;
  }, [data]);

  const pctMetaDiaria = useMemo(() =>
    metaDiaria > 0 ? (fatHoje / metaDiaria) * 100 : 0,
  [fatHoje, metaDiaria]);

  const marcasFiltradas = useMemo(() => {
    if (filtroVendedor && data?.marcas_por_vendedor?.length) {
      return data.marcas_por_vendedor
        .filter(m => m.Vendedor === filtroVendedor)
        .slice(0, 8);
    }
    return marcasMes.slice(0, 8);
  }, [data, filtroVendedor, marcasMes]);

  const filterDefs = useMemo(() => [
    { key: 'Vendedor',   label: 'Vendedor', type: 'select', options: vendedoresOpts },
    { key: 'DescrMarca', label: 'Marca',    type: 'select', options: marcasOpts },
  ], [vendedoresOpts, marcasOpts]);

  const filterValues = useMemo(() => ({
    Vendedor:   filtroVendedor ?? 'todos',
    DescrMarca: filtroMarca   ?? 'todos',
  }), [filtroVendedor, filtroMarca]);

  const pctMeta = metaVal > 0 ? ((kpis.faturamento_atual ?? 0) / metaVal) * 100 : (data?.pct_meta ?? 0);

  function handleFilterChange(newFilters) {
    const newVend  = newFilters.Vendedor   !== 'todos' ? (newFilters.Vendedor   ?? null) : null;
    const newMarca = newFilters.DescrMarca !== 'todos' ? (newFilters.DescrMarca ?? null) : null;
    if (newVend !== filtroVendedor) {
      setFiltroVendedor(newVend);
      setFiltroMarca(null);
    } else if (newMarca !== filtroMarca) {
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
          value={brl(data?.kpi_venda_liquida ?? 0)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
          sub="Venda Líquida (R$)"
        />
        <KpiCard
          label="% da Meta"
          value={pct(pctMeta)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
        />
        <KpiCard label="Ticket Médio" value={brl(kpis.ticket_medio ?? 0)} variant="default" />
        <KpiCard label="Qtde Vendas" value={String(kpis.qtd_vendas_bruta ?? 0)} variant="default" />
        <KpiCard
          label="Devoluções R$"
          value={brl(data?.kpi_devolucoes ?? 0)}
          variant={(data?.kpi_devolucoes ?? 0) > 5000 ? 'error' : 'default'}
        />
        <KpiCard label="Qtde Devoluções" value={String(kpis.qtd_vendas_dev ?? 0)} variant="default" />
        <KpiCard
          label="Margem Bruta"
          value={pct(kpis.pct_margem ?? 0)}
          variant={(kpis.pct_margem ?? 0) >= 30 ? 'success' : (kpis.pct_margem ?? 0) >= 15 ? 'warning' : 'error'}
          sub={brl(kpis.margem_bruta ?? 0)}
        />
        <KpiCard
          label="Meta do Dia"
          value={pct(pctMetaDiaria)}
          variant={pctMetaDiaria >= 100 ? 'success' : pctMetaDiaria >= 70 ? 'warning' : 'error'}
          sub={metaDiaria > 0 ? `${brl(fatHoje)} de ${brl(metaDiaria)}` : 'Meta não configurada'}
          subAbove
        />
      </div>

      {/* ── Novos KPIs financeiros ─────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Documentos Cancelados"
          value={brl(data?.kpi_cancelados ?? 0)}
          variant={(data?.kpi_cancelados ?? 0) > 10000 ? 'error' : 'default'}
        />
        <KpiCard
          label="Faturamento Mês"
          value={brl(data?.kpi_faturamento_bruto ?? 0)}
          sub="Valor Bruto das Vendas (R$)"
          variant="default"
        />
        <KpiCard
          label="Custo Rep Líquida"
          value={brl(data?.kpi_custo_rep ?? 0)}
          variant="default"
        />
        <KpiCard
          label="Lucro Bruto"
          value={brl(data?.kpi_lucro_bruto ?? 0)}
          variant={(data?.kpi_lucro_bruto ?? 0) > 0 ? 'success' : 'error'}
        />
        <KpiCard
          label="Frete"
          value={brl(data?.kpi_frete ?? 0)}
          variant="default"
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
            data={topVendedoresFiltrados}
            xKey="Vendedor"
            bars={[{ key: (filtroMarca && data?.marcas_por_vendedor?.length) ? 'venda_liq_prod' : 'total_venda', label: 'Total', formatter: shortBrl }]}
            horizontal
            showLabels
            highlightKey={filtroVendedor}
            yAxisWidth={vendYAxisWidth}
            height={200}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Faturamento por Marca</h2>
          <PieChart
            data={marcasFiltradas}
            nameKey="DescrMarca"
            valueKey="venda_liq_prod"
            showValue
            formatter={shortBrl}
            height={220}
            highlightKey={filtroMarca}
            tooltipContext={{
              title: 'Venda Líquida Produto',
              formula: 'SUM(vmVndItemDoc.PrecoVndTotItem) — exclui planos 004, 012, 025, 027',
              extra: [
                { key: 'custo_rep_prod', label: 'Custo Rep',   formatter: brl },
                { key: 'lucro_prod',     label: 'Lucro Bruto', formatter: brl },
                { key: 'quantidade',     label: 'Qtd Itens',   formatter: v => (v ?? 0).toLocaleString('pt-BR') },
              ],
            }}
          />
        </div>
        <div className="bg-card border border-card_border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text_main mb-3">Top Itens Mais Vendidos (un.)</h2>
          <BarChart
            data={topItens}
            xKey="DescrItem"
            bars={[{ key: 'quantidade', label: 'Qtd Vendida' }]}
            tooltipExtra={[
              { key: 'DescrMarca',    label: 'Marca' },
              { key: 'venda_liq_prod', label: 'Venda Líquida', formatter: brl },
            ]}
            horizontal
            showLabels
            yAxisWidth={170}
            height={220}
            colors={['#238636']}
          />
        </div>
      </div>
    </div>
  );
}
