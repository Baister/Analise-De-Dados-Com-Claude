import { useState, useEffect, useMemo } from 'react';
import { useDados, useFilteredDados, apiFetch } from '../hooks/useApi';
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

function SectionLabel({ children, first }) {
  return (
    <p
      style={{
        fontSize: 10, color: '#475569', textTransform: 'uppercase',
        letterSpacing: '1px', marginTop: first ? 0 : 18, marginBottom: 8,
      }}
    >
      {children}
    </p>
  );
}

// Card compacto para o waterfall financeiro
function StatCard({ label, sub, value, count = false, color, small = false }) {
  return (
    <div
      className="rounded-lg"
      style={{
        background: '#1e293b',
        borderLeft: `3px solid ${color}`,
        padding: small ? '10px 14px' : '14px 16px',
      }}
    >
      <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 2 }}>
        {label}
      </div>
      {sub && (
        <div style={{ fontSize: 9, color: '#334155', marginBottom: 5 }}>{sub}</div>
      )}
      <div style={{ fontSize: small ? 18 : 22, fontWeight: 700, color, lineHeight: 1.1 }}>
        {count
          ? (value ?? 0).toLocaleString('pt-BR')
          : shortBrl(value ?? 0)
        }
      </div>
    </div>
  );
}

export default function Dashboard({ refreshTrigger }) {
  const [meta, setMeta]                     = useState(null);
  const [filtroVendedor, setFiltroVendedor] = useState(null);
  const [filtroMarca, setFiltroMarca]       = useState(null);

  // Listas globais para os dropdowns — preservadas mesmo quando filtro está ativo
  const [globalVendedores, setGlobalVendedores] = useState([]);
  const [globalMarcas,     setGlobalMarcas]     = useState([]);

  // Filtro server-side: vendedor → chama /dados/dashboard/filtered?vendedor=X
  const filterObj = useMemo(() =>
    filtroVendedor ? { vendedor: filtroVendedor } : {},
  [filtroVendedor]);

  const { data, loading, error, isEmpty } = useFilteredDados('dashboard', filterObj, refreshTrigger);

  // Salva listas globais quando não há filtro de vendedor ativo
  useEffect(() => {
    if (!filtroVendedor) {
      if (data?.top_vendedores?.length) setGlobalVendedores(data.top_vendedores);
      if (data?.marcas_mes?.length)     setGlobalMarcas(data.marcas_mes);
    }
  }, [data, filtroVendedor]);

  useEffect(() => {
    apiFetch('/config').then(d => d && setMeta(d.meta_faturamento_mensal)).catch(() => {});
  }, []);

  // Dropdowns sempre mostram opções globais (mesmo com filtro ativo)
  const topVendedores = globalVendedores.length ? globalVendedores : (data?.top_vendedores ?? []);
  const marcasMes     = globalMarcas.length     ? globalMarcas     : (data?.marcas_mes     ?? []);
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
    // filtroVendedor: server já retornou data filtrado — usar data diretamente
    if (filtroMarca) {
      const marca = marcasMes.find(m => m.DescrMarca === filtroMarca);
      if (marca) {
        const vlp = marca.venda_liq_prod ?? 0;
        const lp  = marca.lucro_prod     ?? 0;
        return {
          ticket_medio:  0,
          margem_bruta:  lp,
          pct_margem:    vlp > 0 ? (lp / vlp) * 100 : 0,
        };
      }
    }
    return {
      ticket_medio:  data.ticket_medio  ?? 0,
      margem_bruta:  data.margem_bruta  ?? 0,
      pct_margem:    (() => { const vb = data.venda_bruta ?? 0; const mb = data.margem_bruta ?? 0; return vb > 0 ? (mb / vb) * 100 : 0; })(),
    };
  }, [data, filtroMarca, marcasMes]);

  const vendedoresOpts   = useMemo(() => getUniqueValues(topVendedores, 'Vendedor'), [topVendedores]);
  const marcasOpts       = useMemo(() => getUniqueValues(marcasMes, 'DescrMarca'),   [marcasMes]);
  const topVendedoresFiltrados = useMemo(() => {
    // Quando marca selecionada: usa marcas_por_vendedor do dado GLOBAL (não filtrado)
    const mvend = globalVendedores.length && data?.marcas_por_vendedor?.length
      ? data.marcas_por_vendedor
      : null;
    if (filtroMarca && mvend) {
      return mvend
        .filter(m => m.DescrMarca === filtroMarca)
        .sort((a, b) => (b.venda_liq_prod ?? 0) - (a.venda_liq_prod ?? 0))
        .slice(0, 10);
    }
    return topVendedores.slice(0, 10);
  }, [data, filtroMarca, topVendedores, globalVendedores]);

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

  // pctMeta: usa kpi_venda_liquida do dado filtrado (server-side quando vendedor ativo)
  const pctMeta = metaVal > 0 ? ((data?.kpi_venda_liquida ?? 0) / metaVal) * 100 : (data?.pct_meta ?? 0);

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
    ? `Vendedor: ${filtroVendedor.trim()}`
    : filtroMarca ? `Marca: ${filtroMarca}` : null;

  const fatChartTitle = filtroVendedor
    ? `Faturamento Diário — ${filtroVendedor.trim()}`
    : filtroMarca ? `Faturamento Diário — ${filtroMarca}` : 'Faturamento Diário';

  const lucroColor = (data?.kpi_lucro_bruto ?? 0) > 0 ? '#10b981' : '#ef4444';

  return (
    <div style={{ padding: 16 }}>

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', margin: 0 }}>Dashboard</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {filtroLabel && (
            <span style={{
              fontSize: 11, padding: '2px 10px', borderRadius: 4,
              background: 'rgba(59,130,246,0.12)', color: '#93c5fd', border: '1px solid rgba(59,130,246,0.25)',
            }}>
              {filtroLabel}
            </span>
          )}
          {data?.ultimo_update && (
            <span style={{ fontSize: 10, color: '#334155' }}>Atualizado: {data.ultimo_update}</span>
          )}
        </div>
      </div>

      {/* ── Resultado Comercial do Mês ──────────────────────────────── */}
      <SectionLabel first>Resultado Comercial do Mês</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, alignItems: 'start' }}>

        {/* Col 1: Faturamento Bruto → Qtde Vendas */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <StatCard
            label="Faturamento do Mês"
            sub="Valor Bruto das Vendas (R$)"
            value={data?.kpi_faturamento_bruto}
            color="#3b82f6"
          />
          <StatCard
            label="Qtde Vendas"
            value={data?.qtd_vendas_bruta}
            color="#475569"
            count
            small
          />
        </div>

        {/* Col 2: Devoluções → Qtde Devoluções */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <StatCard
            label="Devoluções"
            sub="vmMetricasMotivoDevItem"
            value={data?.kpi_devolucoes}
            color="#f59e0b"
          />
          <StatCard
            label="Qtde Devoluções"
            value={data?.qtd_vendas_dev}
            color="#78716c"
            count
            small
          />
        </div>

        {/* Col 3: Documentos Cancelados → Lucro Bruto */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <StatCard
            label="Documentos Cancelados"
            sub="vwVndDoc — TipoMovimento 1.5"
            value={data?.kpi_cancelados}
            color="#ef4444"
          />
          <StatCard
            label="Lucro Bruto"
            value={data?.kpi_lucro_bruto}
            color={lucroColor}
            small
          />
        </div>

        {/* Col 4: Faturamento Líquido → Custo Rep */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <StatCard
            label="Faturamento do Mês"
            sub="Venda Líquida (R$)"
            value={data?.kpi_venda_liquida}
            color="#22c55e"
          />
          <StatCard
            label="Custo Rep Líquida"
            value={data?.kpi_custo_rep}
            color="#a855f7"
            small
          />
        </div>

      </div>

      {/* ── Performance ─────────────────────────────────────────────── */}
      <SectionLabel>Performance</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10 }}>
        <KpiCard
          label="% da Meta"
          value={pct(pctMeta)}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
          topBorder="#3b82f6"
        />
        <KpiCard
          label="Meta do Dia"
          value={pct(pctMetaDiaria)}
          variant={pctMetaDiaria >= 100 ? 'success' : pctMetaDiaria >= 70 ? 'warning' : 'error'}
          sub={metaDiaria > 0 ? `${brl(fatHoje)} de ${brl(metaDiaria)}` : 'Meta não configurada'}
          subAbove
          topBorder="#f59e0b"
        />
        <KpiCard
          label="Ticket Médio"
          value={brl(data?.ticket_medio ?? 0)}
          variant="default"
          topBorder="#64748b"
        />
        <KpiCard
          label="Frete"
          value={brl(data?.kpi_frete ?? 0)}
          variant="default"
          topBorder="#64748b"
        />
      </div>

      {/* ── Filtros ─────────────────────────────────────────────────── */}
      <div style={{ marginTop: 14 }}>
        <FilterBar filters={filterDefs} values={filterValues} onChange={handleFilterChange} />
      </div>

      {/* ── Análise Diária ──────────────────────────────────────────── */}
      <SectionLabel>Análise Diária</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>

        <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
          <p style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 12 }}>
            {fatChartTitle}
          </p>
          <LineChart
            data={fatDiario}
            xKey="dia"
            lines={[{ key: 'faturamento', label: 'Faturamento', formatter: shortBrl }]}
            height={200}
          />
        </div>

        <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
          <p style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 12 }}>
            Top Vendedores
          </p>
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

      {/* ── Marcas &amp; Produtos ────────────────────────────────────── */}
      <SectionLabel>Marcas &amp; Produtos</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>

        <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
          <p style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 12 }}>
            Faturamento por Marca
          </p>
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

        <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
          <p style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 12 }}>
            Top Itens Mais Vendidos (un.)
          </p>
          <BarChart
            data={topItens}
            xKey="DescrItem"
            bars={[{ key: 'quantidade', label: 'Qtd Vendida' }]}
            tooltipExtra={[
              { key: 'DescrMarca',     label: 'Marca' },
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

      {data?.ultimo_update && (
        <p style={{ fontSize: 10, color: '#334155', textAlign: 'center', marginTop: 14 }}>
          Atualizado: {data.ultimo_update}
        </p>
      )}

    </div>
  );
}
