import { useState, useEffect, useMemo } from 'react';
import { useDados, apiFetch } from '../hooks/useApi';
import { useMetas } from '../hooks/useMetas';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import LineChart from '../charts/LineChart';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, pct, shortBrl } from '../utils/format';
import { getUniqueValues, agregaPorDia } from '../utils/filters';
import { remainingBusinessDaysSP } from '../utils/businessDays';

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
      <div style={{ fontSize: 9, color: '#f1f5f9', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 2 }}>
        {label}
      </div>
      {sub && (
        <div style={{ fontSize: 9, color: '#334155', marginBottom: 5 }}>{sub}</div>
      )}
      <div style={{ fontSize: small ? 18 : 22, fontWeight: 700, color, lineHeight: 1.1 }}>
        {value == null
          ? '—'
          : count
            ? value.toLocaleString('pt-BR')
            : brl(value)
        }
      </div>
    </div>
  );
}

export default function Dashboard({ refreshTrigger }) {
  const [meta, setMeta]                     = useState(null);
  const [filtroVendedor, setFiltroVendedor] = useState(null);
  const [filtroMarca, setFiltroMarca]       = useState(null);

  // Filtragem 100% client-side (padrão da aba Vendas) — payload global único
  const { data, loading, error, isEmpty } = useDados('dashboard', refreshTrigger);
  const { metas } = useMetas();
  const mIndiv = metas?.metas_individuais ?? {};

  useEffect(() => {
    apiFetch('/config').then(d => d && setMeta(d.meta_faturamento_mensal)).catch(() => {});
  }, []);

  const topVendedores = useMemo(() => data?.top_vendedores ?? [], [data]);
  const marcasMes     = useMemo(() => data?.marcas_mes ?? [],     [data]);

  // KPI ativo: registro do vendedor OU da marca qdo filtrado; senão escalares globais.
  // (kpis_por_marca traz kpi_cancelados/kpi_frete = null → "—", pois são de nível-documento)
  const kpiAtivo = useMemo(() => {
    if (filtroVendedor) {
      return (data?.kpis_por_vendedor ?? []).find(v => v.Vendedor === filtroVendedor) ?? {};
    }
    if (filtroMarca) {
      return (data?.kpis_por_marca ?? []).find(m => m.DescrMarca === filtroMarca) ?? {};
    }
    return data ?? {};
  }, [data, filtroVendedor, filtroMarca]);

  // Top itens: por vendedor / por marca (dict) qdo filtrado; senão global
  const topItens = useMemo(() => {
    if (filtroVendedor) return (data?.top_itens_por_vendedor?.[filtroVendedor] ?? []).slice(0, 8);
    if (filtroMarca)    return (data?.top_itens_por_marca?.[filtroMarca] ?? []).slice(0, 8);
    return (data?.top_itens_mes ?? []).slice(0, 8);
  }, [data, filtroVendedor, filtroMarca]);

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

  const vendedoresOpts   = useMemo(() => getUniqueValues(topVendedores, 'Vendedor'), [topVendedores]);
  const marcasOpts       = useMemo(() => getUniqueValues(marcasMes, 'DescrMarca'),   [marcasMes]);

  const hasMarcasVend = Boolean(data?.marcas_por_vendedor?.length);
  const topVendedoresFiltrados = useMemo(() => {
    if (filtroMarca && hasMarcasVend) {
      return data.marcas_por_vendedor
        .filter(m => m.DescrMarca === filtroMarca)
        .sort((a, b) => (b.venda_liq_prod ?? 0) - (a.venda_liq_prod ?? 0))
        .slice(0, 10);
    }
    if (filtroVendedor) return topVendedores.filter(v => v.Vendedor === filtroVendedor);
    return topVendedores.slice(0, 10);
  }, [data, filtroMarca, filtroVendedor, hasMarcasVend, topVendedores]);

  const vendYAxisWidth   = useMemo(() => {
    const src = filtroMarca ? topVendedoresFiltrados : topVendedores;
    const longest = src.reduce((max, v) => Math.max(max, (v.Vendedor ?? '').length), 0);
    return Math.min(160, Math.max(90, longest * 7));
  }, [filtroMarca, topVendedoresFiltrados, topVendedores]);

  const metaVal = useMemo(() => {
    if (filtroVendedor) {
      const m = Object.entries(mIndiv).find(
        ([k]) => k.trim().toLowerCase() === filtroVendedor.trim().toLowerCase()
      )?.[1];
      return m ?? 0;                       // 0 → "sem meta individual"
    }
    // Meta da empresa: prioriza a "Meta Mensal Total" definida em Configurações
    // (metas.json via useMetas); senão cai para /config (meta_faturamento_mensal).
    return (metas?.meta_mensal_total || 0) > 0
      ? metas.meta_mensal_total
      : (meta ?? data?.meta_mensal ?? 0);
  }, [filtroVendedor, mIndiv, metas, meta, data]);

  // Realizado no mês (na mesma base da meta: venda líquida do KPI ativo)
  const realizadoMes = kpiAtivo.kpi_venda_liquida ?? 0;

  // Meta do Dia DINÂMICA: o que FALTA para a meta ÷ dias úteis RESTANTES
  // (igual ao "Progresso Diário" da aba Vendas). Cai conforme você vende.
  const metaDiaria = useMemo(() => {
    if (!metaVal) return 0;
    const restante = Math.max(metaVal - realizadoMes, 0);
    const now = new Date();
    return restante / Math.max(remainingBusinessDaysSP(now.getFullYear(), now.getMonth() + 1), 1);
  }, [metaVal, realizadoMes]);

  const fatHoje = useMemo(() => {
    const hoje = new Date().toISOString().slice(0, 10);
    const entry = fatDiario.find(r => String(r.dia).slice(0, 10) === hoje);
    return entry?.faturamento ?? 0;
  }, [fatDiario]);

  // Meta mensal já batida → 100%; senão, faturado hoje ÷ meta diária ajustada
  const metaMensalBatida = metaVal > 0 && realizadoMes >= metaVal;
  const pctMetaDiaria = useMemo(() => {
    if (metaMensalBatida) return 100;
    return metaDiaria > 0 ? (fatHoje / metaDiaria) * 100 : 0;
  }, [metaMensalBatida, fatHoje, metaDiaria]);

  const marcasFiltradas = useMemo(() => {
    if (filtroVendedor && hasMarcasVend) {
      return data.marcas_por_vendedor.filter(m => m.Vendedor === filtroVendedor).slice(0, 8);
    }
    return marcasMes.slice(0, 8);
  }, [data, filtroVendedor, hasMarcasVend, marcasMes]);

  const filterDefs = useMemo(() => [
    { key: 'Vendedor',   label: 'Vendedor', type: 'select', options: vendedoresOpts },
    { key: 'DescrMarca', label: 'Marca',    type: 'select', options: marcasOpts },
  ], [vendedoresOpts, marcasOpts]);

  const filterValues = useMemo(() => ({
    Vendedor:   filtroVendedor ?? 'todos',
    DescrMarca: filtroMarca   ?? 'todos',
  }), [filtroVendedor, filtroMarca]);

  // pctMeta: venda líquida do KPI ativo (vendedor ou global) ÷ meta (individual ou empresa)
  const pctMeta = metaVal > 0 ? ((kpiAtivo.kpi_venda_liquida ?? 0) / metaVal) * 100 : 0;

  // Margem Bruta = Lucro Bruto / Faturamento Líquido (reflete vendedor/marca via kpiAtivo)
  const margemBruta = (kpiAtivo.kpi_venda_liquida ?? 0) > 0
    ? ((kpiAtivo.kpi_lucro_bruto ?? 0) / kpiAtivo.kpi_venda_liquida) * 100
    : 0;
  // Faixas: >=30 verde | 25–29,99 amarelo | <25 (inclui 20–24,99) vermelho
  const margemCor = margemBruta >= 30 ? '#22c55e' : margemBruta >= 25 ? '#f59e0b' : '#ef4444';

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

  const nomeVend = (filtroVendedor ?? '').trim();

  const filtroLabel = filtroVendedor
    ? `Vendedor: ${nomeVend}`
    : filtroMarca ? `Marca: ${filtroMarca}` : null;

  const fatChartTitle = filtroVendedor
    ? `Faturamento Diário — ${nomeVend}`
    : filtroMarca ? `Faturamento Diário — ${filtroMarca}` : 'Faturamento Diário';

  const lucroColor = (kpiAtivo.kpi_lucro_bruto ?? 0) > 0 ? '#10b981' : '#ef4444';

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
            label="Faturamento Bruto"
            sub="Valor Bruto das Vendas (R$)"
            value={kpiAtivo.kpi_faturamento_bruto}
            color="#3b82f6"
          />
          <StatCard
            label="Quantidade de Vendas"
            value={kpiAtivo.qtd_vendas_bruta}
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
            value={kpiAtivo.kpi_devolucoes}
            color="#f59e0b"
          />
          <StatCard
            label="Quantidade de Devoluções"
            value={kpiAtivo.qtd_vendas_dev}
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
            value={kpiAtivo.kpi_cancelados}
            color="#ef4444"
          />
          <StatCard
            label="Lucro Bruto"
            value={kpiAtivo.kpi_lucro_bruto}
            color={lucroColor}
            small
          />
        </div>

        {/* Col 4: Faturamento Líquido → Custo Rep */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <StatCard
            label="Faturamento Líquido Mês"
            sub="Venda Líquida (R$)"
            value={kpiAtivo.kpi_venda_liquida}
            color="#22c55e"
          />
          <StatCard
            label="Custo de Reposição Líquida"
            value={kpiAtivo.kpi_custo_rep}
            color="#a855f7"
            small
          />
        </div>

      </div>

      {/* ── Performance ─────────────────────────────────────────────── */}
      <SectionLabel>Performance</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10 }}>
        <KpiCard
          label="% da Meta"
          value={pct(pctMeta)}
          sub={metaVal > 0 ? `Meta: ${brl(metaVal)}`
                : (filtroVendedor ? 'sem meta individual' : 'Meta não configurada')}
          variant={pctMeta >= 100 ? 'success' : pctMeta >= 70 ? 'warning' : 'error'}
          topBorder="#3b82f6"
          labelColor="#f1f5f9"
        />
        <KpiCard
          label="Meta do Dia"
          value={pct(pctMetaDiaria)}
          variant={pctMetaDiaria >= 100 ? 'success' : pctMetaDiaria >= 70 ? 'warning' : 'error'}
          sub={
            metaVal <= 0 ? 'Meta não configurada'
            : metaMensalBatida ? 'Meta do mês atingida 🎉'
            : `${brl(fatHoje)} de ${brl(metaDiaria)} hoje`
          }
          subAbove
          topBorder="#f59e0b"
          labelColor="#f1f5f9"
        />
        <KpiCard
          label="Margem Bruta"
          value={pct(margemBruta)}
          valueColor={margemCor}
          gradient={`${margemCor}33`}
          topBorder={margemCor}
          labelColor="#f1f5f9"
        />
        <KpiCard
          label="Ticket Médio"
          value={brl(kpiAtivo.ticket_medio ?? 0)}
          variant="default"
          topBorder="#64748b"
          labelColor="#f1f5f9"
        />
        <KpiCard
          label="Frete"
          value={kpiAtivo.kpi_frete == null ? '—' : brl(kpiAtivo.kpi_frete)}
          variant="default"
          topBorder="#64748b"
          labelColor="#f1f5f9"
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
            {filtroVendedor ? `Vendedor — ${nomeVend}` : filtroMarca ? `Vendedores — ${filtroMarca}` : 'Top Vendedores'}
          </p>
          <BarChart
            data={topVendedoresFiltrados}
            xKey="Vendedor"
            bars={[{ key: (filtroMarca && data?.marcas_por_vendedor?.length) ? 'venda_liq_prod' : 'total_venda', label: 'Total', formatter: shortBrl }]}
            horizontal
            showLabels
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
            {filtroVendedor ? `Top Itens — ${nomeVend}` : filtroMarca ? `Top Itens — ${filtroMarca}` : 'Top Itens Mais Vendidos (un.)'}
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
