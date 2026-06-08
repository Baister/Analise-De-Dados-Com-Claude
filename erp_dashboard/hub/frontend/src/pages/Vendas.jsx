import { useState, useMemo } from 'react';
import { useDados } from '../hooks/useApi';
import { useMetas } from '../hooks/useMetas';
import KpiCard from '../components/KpiCard';
import FilterBar from '../components/FilterBar';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, pct, shortBrl } from '../utils/format';
import { getUniqueValues } from '../utils/filters';
import { countBusinessDaysSP, remainingBusinessDaysSP } from '../utils/businessDays';

function SectionHeader({ title, subtitle }) {
  return (
    <div className="flex items-baseline gap-3 mb-3">
      <h2 className="text-sm font-semibold text-text_main">{title}</h2>
      {subtitle && <span className="text-xs text-subtext">{subtitle}</span>}
    </div>
  );
}

function progressColor(pct) {
  if (pct >= 100) return '#238636';
  if (pct >= 70)  return '#d29922';
  return '#da3633';
}

export default function Vendas({ refreshTrigger }) {
  const [filtroVendedor, setFiltroVendedor] = useState(null);
  const [filtroMarca, setFiltroMarca]       = useState(null);

  const { data, loading, error, isEmpty } = useDados('vendas', refreshTrigger);

  const topVendedores = useMemo(() => data?.top_vendedores ?? [], [data]);
  const marcasMes     = useMemo(() => data?.marcas_mes     ?? [], [data]);

  /* ── Metas individuais ────────────────────────────────────────── */
  const { metas } = useMetas();
  const mIndividuais = metas?.metas_individuais ?? {};
  const hasMetas = Object.keys(mIndividuais).length > 0;

  const vendaHojeMap = useMemo(() => {
    const arr = data?.venda_hoje_vendedor ?? [];
    return Object.fromEntries(arr.map(r => [r.Vendedor, r.venda_hoje ?? 0]));
  }, [data]);

  const topVendedoresMap = useMemo(() =>
    Object.fromEntries(topVendedores.map(v => [v.Vendedor, v])),
    [topVendedores]
  );

  const diasRestantes = useMemo(() => {
    const now = new Date();
    return remainingBusinessDaysSP(now.getFullYear(), now.getMonth() + 1);
  }, []);

  const metaDiariaMap = useMemo(() => {
    return Object.fromEntries(
      Object.entries(mIndividuais).map(([v, meta]) => {
        const realizado = topVendedoresMap[v]?.total_venda ?? 0;
        const restante  = Math.max(meta - realizado, 0);
        return [v, restante / Math.max(diasRestantes, 1)];
      })
    );
  }, [mIndividuais, topVendedoresMap, diasRestantes]);

  /* ── KPIs ─────────────────────────────────────────────────────── */
  const kpis = useMemo(() => {
    if (!data) return {};

    if (filtroVendedor) {
      const vend = topVendedores.find(v => v.Vendedor === filtroVendedor);
      if (vend) {
        const vb = vend.total_venda  ?? 0;
        const mb = vend.margem_bruta ?? 0;
        return {
          faturamento_atual: vb,
          qtd_documentos:    vend.qtd_pedidos    ?? 0,
          ticket_medio:      vend.ticket_medio   ?? 0,
          devolucao:         vend.devolucao      ?? 0,
          qtd_devolucoes:    vend.qtd_devolucoes ?? 0,
          margem_bruta:      mb,
          pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
          clientes_ativos:   null,
        };
      }
    }

    if (filtroMarca) {
      const marca = marcasMes.find(m => m.DescrMarca === filtroMarca);
      if (marca) {
        const vb  = marca.faturamento    ?? 0;
        const mb  = marca.margem_bruta   ?? 0;
        const qtd = marca.qtd_documentos ?? 0;
        return {
          faturamento_atual: vb,
          qtd_documentos:    qtd,
          ticket_medio:      qtd > 0 ? vb / qtd : 0,
          devolucao:         marca.devolucao      ?? 0,
          qtd_devolucoes:    marca.qtd_devolucoes ?? 0,
          margem_bruta:      mb,
          pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
          clientes_ativos:   null,
        };
      }
    }

    const vb = data.faturamento_atual ?? 0;
    const mb = data.margem_total      ?? 0;
    return {
      faturamento_atual: vb,
      qtd_documentos:    data.qtd_documentos ?? 0,
      ticket_medio:      data.ticket_medio   ?? 0,
      devolucao:         data.devolucao      ?? 0,
      qtd_devolucoes:    data.qtd_devolucoes ?? 0,
      margem_bruta:      mb,
      pct_margem:        vb > 0 ? (mb / vb) * 100 : 0,
      clientes_ativos:   data.clientes_ativos ?? 0,
    };
  }, [data, filtroVendedor, filtroMarca, topVendedores, marcasMes]);

  /* ── Dados filtrados para os gráficos ─────────────────────────── */
  const hasMarcasVend = Boolean(data?.marcas_por_vendedor?.length);

  const marcasFiltradas = useMemo(() => {
    if (filtroVendedor && hasMarcasVend) {
      return data.marcas_por_vendedor.filter(m => m.Vendedor === filtroVendedor).slice(0, 8);
    }
    return marcasMes.slice(0, 8);
  }, [data, filtroVendedor, hasMarcasVend, marcasMes]);

  const topVendedoresFiltrados = useMemo(() => {
    if (filtroMarca && hasMarcasVend) {
      return data.marcas_por_vendedor
        .filter(m => m.DescrMarca === filtroMarca)
        .sort((a, b) => b.faturamento - a.faturamento)
        .slice(0, 10);
    }
    return topVendedores.slice(0, 10);
  }, [data, filtroMarca, hasMarcasVend, topVendedores]);

  // Dados do bar "Top Vendedores": 👑 no Top 1 (índice 0, exceto ao filtrar 1 vendedor)
  // + _fat_liq (faturamento líquido = bruto + devolução) para o tooltip.
  const topVendData = useMemo(() => topVendedoresFiltrados.map((v, i) => ({
    ...v,
    _disp: (!filtroVendedor && i === 0 ? '👑 ' : '') + (v.Vendedor ?? ''),
    _fat_liq: (v.total_venda ?? 0) + (v.devolucao ?? 0),
  })), [topVendedoresFiltrados, filtroVendedor]);

  const ticketFiltrado = useMemo(() => {
    if (filtroVendedor) return topVendedores.filter(v => v.Vendedor === filtroVendedor);
    if (filtroMarca)    return [];
    return (data?.ticket_medio_vendedor ?? []).slice(0, 10);
  }, [data, filtroVendedor, filtroMarca, topVendedores]);

  const itensMarca = useMemo(() => {
    if (!filtroMarca || !data?.top_itens_por_marca) return [];
    return data.top_itens_por_marca[filtroMarca] ?? [];
  }, [data, filtroMarca]);

  const itensVendedor = useMemo(() => {
    if (!filtroVendedor || !data?.top_itens_por_vendedor) return [];
    return data.top_itens_por_vendedor[filtroVendedor] ?? [];
  }, [data, filtroVendedor]);

  /* ── Opções dos filtros ────────────────────────────────────────── */
  const vendedoresOpts = useMemo(() => getUniqueValues(topVendedores, 'Vendedor'), [topVendedores]);
  const marcasOpts     = useMemo(() => getUniqueValues(marcasMes, 'DescrMarca'),   [marcasMes]);

  const vendYAxisWidth = useMemo(() => {
    const src = filtroMarca ? topVendedoresFiltrados : topVendedores;
    const longest = src.reduce((max, v) => Math.max(max, (v.Vendedor ?? '').length), 0);
    return Math.min(160, Math.max(90, longest * 7));
  }, [filtroMarca, topVendedoresFiltrados, topVendedores]);

  const filterDefs = useMemo(() => [
    { key: 'Vendedor',   label: 'Vendedor', type: 'select', options: vendedoresOpts },
    { key: 'DescrMarca', label: 'Marca',    type: 'select', options: marcasOpts },
  ], [vendedoresOpts, marcasOpts]);

  const filterValues = useMemo(() => ({
    Vendedor:   filtroVendedor ?? 'todos',
    DescrMarca: filtroMarca   ?? 'todos',
  }), [filtroVendedor, filtroMarca]);

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

  /* ── Estados de carregamento ──────────────────────────────────── */
  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      Carregando dados de vendas…
    </div>
  );

  if (error && !data) return (
    <div className="flex items-center justify-center h-64 text-accent_red text-sm">
      Erro ao carregar dados: {error}
    </div>
  );

  if (isEmpty) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      <div className="text-center space-y-1">
        <p>Bot Vendas está processando dados do banco…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  );

  /* ── Textos dinâmicos dos gráficos ────────────────────────────── */
  const filtroLabel = filtroVendedor
    ? `Vendedor: ${filtroVendedor}`
    : filtroMarca ? `Marca: ${filtroMarca}` : null;

  const barKey         = (filtroMarca && hasMarcasVend) ? 'faturamento' : 'total_venda';
  const barTitle       = filtroMarca ? `Vendedores — ${filtroMarca}` : 'Top Vendedores';
  const marcaFatTitle  = filtroVendedor ? `Marcas — ${filtroVendedor}` : 'Faturamento por Marca';
  const marcaQtdTitle  = filtroVendedor ? `Itens Vendidos — ${filtroVendedor}` : 'Itens Vendidos por Marca';

  // Margem Bruta — faixas de cor (igual Dashboard): >=30 verde | 25–29,99 amarelo | <25 vermelho
  const margemCor = (kpis.pct_margem ?? 0) >= 30 ? '#22c55e'
    : (kpis.pct_margem ?? 0) >= 25 ? '#f59e0b' : '#ef4444';
  const devVariant    = Math.abs(kpis.devolucao ?? 0) > 5000 ? 'error' : 'default';

  return (
    <div className="p-6 space-y-6">

      {/* ── Cabeçalho ─────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-text_main">Vendas</h1>
          {filtroLabel && (
            <span className="inline-flex items-center gap-1.5 text-xs bg-blue-900/40 text-blue-300 border border-blue-700/40 px-2.5 py-1 rounded-full font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 inline-block" />
              {filtroLabel}
            </span>
          )}
        </div>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* ── KPIs — linha 1: faturamento bruto + devolução + margem ──── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Faturamento do Mês Bruto" value={brl(kpis.faturamento_atual ?? 0)} variant="default" />
        <KpiCard
          label="Devolução R$"
          value={brl(Math.abs(kpis.devolucao ?? 0))}
          variant={devVariant}
        />
        <KpiCard
          label="Margem Bruta"
          value={pct(kpis.pct_margem ?? 0)}
          valueColor={margemCor}
          gradient={`${margemCor}33`}
          topBorder={margemCor}
          sub={brl(kpis.margem_bruta ?? 0)}
        />
        <KpiCard label="Ticket Médio" value={brl(kpis.ticket_medio ?? 0)} variant="default" />
      </div>

      {/* ── KPIs — linha 2: operacional ───────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Nº Documentos"  value={String(kpis.qtd_documentos ?? 0)} variant="default" />
        <KpiCard label="Nº Devoluções"  value={String(kpis.qtd_devolucoes ?? 0)} variant="default" />
        <KpiCard
          label="Clientes Ativos"
          value={kpis.clientes_ativos !== null ? String(kpis.clientes_ativos) : '—'}
          variant="default"
        />
        <KpiCard label="Total Marcas"   value={String(marcasMes.length)}          variant="default" />
      </div>

      {/* ── Filtros ────────────────────────────────────────────────── */}
      <FilterBar filters={filterDefs} values={filterValues} onChange={handleFilterChange} />

      {/* ── Gráficos — Barras (vendedores) ────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-card_border rounded-xl p-4">
          <SectionHeader
            title={barTitle}
            subtitle={filtroMarca ? 'faturamento nesta marca' : 'por faturamento bruto · 👑 = Top 1'}
          />
          <BarChart
            data={topVendData}
            xKey="_disp"
            bars={[{ key: barKey, label: 'Total', formatter: shortBrl }]}
            tooltipExtra={[
              { key: 'qtd_pedidos',    label: 'Qtd Vendas' },
              { key: 'qtd_devolucoes', label: 'Qtd Devoluções' },
              { key: '_fat_liq',       label: 'Fat. Líquido', formatter: brl },
            ]}
            horizontal
            showLabels
            highlightKey={filtroVendedor}
            yAxisWidth={vendYAxisWidth + 16}
            height={240}
          />
        </div>

        <div className="bg-card border border-card_border rounded-xl p-4">
          {ticketFiltrado.length > 0 ? (
            <>
              <SectionHeader
                title="Ticket Médio por Vendedor"
                subtitle={filtroVendedor ? filtroVendedor : 'top 10'}
              />
              <BarChart
                data={ticketFiltrado}
                xKey="Vendedor"
                bars={[{ key: 'ticket_medio', label: 'Ticket', formatter: shortBrl }]}
                horizontal
                showLabels
                highlightKey={filtroVendedor}
                yAxisWidth={vendYAxisWidth}
                height={240}
              />
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-subtext text-xs">
              Selecione "Todos os vendedores" para ver o ranking de ticket médio.
            </div>
          )}
        </div>
      </div>

      {/* ── Gráficos — Pizzas lado a lado ─────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pizza 1 — Faturamento por Marca */}
        <div className="bg-card border border-card_border rounded-xl p-4">
          <SectionHeader
            title={marcaFatTitle}
            subtitle={filtroVendedor ? 'marcas vendidas por este vendedor' : 'top 8 do mês'}
          />
          <PieChart
            data={marcasFiltradas}
            nameKey="DescrMarca"
            valueKey="faturamento"
            showValue
            formatter={shortBrl}
            height={240}
            highlightKey={filtroMarca}
          />
        </div>

        {/* Pizza 2 — Itens (drill-down conforme filtro) */}
        <div className="bg-card border border-card_border rounded-xl p-4">
          {filtroVendedor && itensVendedor.length > 0 ? (
            <>
              <SectionHeader title={`Top Itens — ${filtroVendedor}`} subtitle="por faturamento no mês" />
              <PieChart data={itensVendedor} nameKey="DescrItem" valueKey="faturamento" showValue formatter={shortBrl} height={240} />
            </>
          ) : filtroMarca && itensMarca.length > 0 ? (
            <>
              <SectionHeader title={`Top Itens — ${filtroMarca}`} subtitle="por faturamento no mês" />
              <PieChart data={itensMarca} nameKey="DescrItem" valueKey="faturamento" showValue formatter={shortBrl} height={240} />
            </>
          ) : (
            <>
              <SectionHeader title={marcaQtdTitle} subtitle="unidades vendidas" />
              <PieChart data={marcasFiltradas} nameKey="DescrMarca" valueKey="quantidade" showValue height={240} highlightKey={filtroMarca} />
            </>
          )}
        </div>
      </div>

      {/* ── Progresso de Metas ────────────────────────────────────────── */}
      {hasMetas && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* Mensal */}
          <div className="bg-card border border-card_border rounded-xl p-4">
            <SectionHeader
              title="Progresso Mensal"
              subtitle={`meta individual — ${new Date().toLocaleString('pt-BR', { month: 'long' })}`}
            />
            <div className="space-y-3">
              {topVendedores
                .filter(v => (mIndividuais[v.Vendedor] ?? 0) > 0)
                .map(v => {
                  const meta   = mIndividuais[v.Vendedor];
                  const real   = v.total_venda ?? 0;
                  const pctVal = Math.min((real / meta) * 100, 100);
                  const cor    = progressColor(pctVal);
                  return (
                    <div key={v.Vendedor}>
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="text-xs text-text_main truncate max-w-[55%]">{v.Vendedor}</span>
                        <span className="text-xs font-bold" style={{ color: cor }}>
                          {Math.round(pctVal)}% · {shortBrl(real)} / {shortBrl(meta)}
                        </span>
                      </div>
                      <div className="h-2 bg-card_border rounded-full">
                        <div
                          className="h-2 rounded-full transition-all"
                          style={{ width: `${pctVal}%`, background: cor }}
                        />
                      </div>
                    </div>
                  );
                })}
              {topVendedores.filter(v => (mIndividuais[v.Vendedor] ?? 0) > 0).length === 0 && (
                <p className="text-xs text-subtext">Nenhum vendedor da lista tem meta configurada.</p>
              )}
            </div>
          </div>

          {/* Diário */}
          <div className="bg-card border border-card_border rounded-xl p-4">
            <SectionHeader
              title="Progresso Diário"
              subtitle={`meta ajustada pelo restante · ${diasRestantes} dia${diasRestantes !== 1 ? 's' : ''} útil${diasRestantes !== 1 ? 'eis' : ''} restante${diasRestantes !== 1 ? 's' : ''}`}
            />
            <div className="space-y-3">
              {topVendedores
                .filter(v => (mIndividuais[v.Vendedor] ?? 0) > 0)
                .map(v => {
                  const metaM    = mIndividuais[v.Vendedor];
                  const real     = v.total_venda ?? 0;
                  const exceeded = real >= metaM;
                  const metaD    = metaDiariaMap[v.Vendedor] ?? 0;
                  const hoje     = vendaHojeMap[v.Vendedor]  ?? 0;
                  const pctVal   = exceeded ? 100 : (metaD > 0 ? Math.min((hoje / metaD) * 100, 100) : 0);
                  const cor      = progressColor(pctVal);
                  return (
                    <div key={v.Vendedor}>
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="text-xs text-text_main truncate max-w-[45%]">{v.Vendedor}</span>
                        <span className="text-xs font-bold" style={{ color: cor }}>
                          {exceeded
                            ? `meta atingida · ${shortBrl(hoje)} hoje`
                            : `${Math.round(pctVal)}% · ${shortBrl(hoje)} hoje · meta ${shortBrl(metaD)}`}
                        </span>
                      </div>
                      <div className="h-2 bg-card_border rounded-full">
                        <div
                          className="h-2 rounded-full transition-all"
                          style={{ width: `${pctVal}%`, background: cor }}
                        />
                      </div>
                    </div>
                  );
                })}
              {topVendedores.filter(v => (mIndividuais[v.Vendedor] ?? 0) > 0).length === 0 && (
                <p className="text-xs text-subtext">Configure metas individuais na aba Configurações.</p>
              )}
            </div>
          </div>

        </div>
      )}

    </div>
  );
}
