import { useMemo } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import { useMetas } from '../hooks/useMetas';
import KpiCard from '../components/KpiCard';
import BarChart from '../charts/BarChart';
import AreaChart from '../charts/AreaChart';
import DataTable from '../components/DataTable';
import { brl, shortBrl, pct, fmtDate } from '../utils/format';

function fmtDelta(delta, unit = '') {
  if (delta === 0 || delta == null) return null;
  const abs = Math.abs(delta);
  return delta > 0 ? `↑ +${abs}${unit} vs mês ant.` : `↓ ${abs}${unit} vs mês ant.`;
}

const RANKING_COLS = [
  { key: 'Vendedor',        label: 'Vendedor' },
  { key: 'propostas',       label: 'Propostas',   render: v => String(v ?? 0) },
  { key: 'convertidos',     label: 'Convertidos', render: v => String(v ?? 0) },
  { key: 'taxa_conv',       label: 'Taxa',        render: v => pct(v ?? 0) },
  { key: 'valor_convertido',label: 'Valor',       render: v => shortBrl(v) },
  { key: 'ticket_medio',    label: 'Ticket',      render: v => shortBrl(v) },
  { key: '_pct_meta',       label: '% Meta',      render: v => v != null ? pct(v) : '—' },
];

const RISCO_COLS = [
  { key: 'nome_cliente',   label: 'Cliente' },
  { key: 'dias_inativo',   label: 'Dias',          render: v => String(v ?? 0) },
  { key: 'ultimo_vendedor', label: 'Ult. Vendedor' },
];

const TOP_COLS = [
  { key: 'nome_cliente', label: 'Cliente' },
  { key: 'valor_mes',    label: 'Valor',   render: v => shortBrl(v) },
  { key: 'vendedor',     label: 'Vendedor' },
  { key: 'pedidos',      label: 'Pedidos', render: v => String(v ?? 0) },
];

const INAT_COLS = [
  { key: 'nome_cliente',          label: 'Cliente' },
  { key: 'dias_inativo',          label: 'Dias',          render: v => String(v ?? 0) },
  { key: 'ultima_compra',         label: 'Última Compra', render: v => fmtDate(v) },
  { key: 'ultimo_vendedor',       label: 'Ult. Vendedor' },
  { key: 'faturamento_historico', label: 'Fat. Histórico', render: v => brl(v) },
];

export default function CRM({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('crm', {}, refreshTrigger);
  const { metas } = useMetas();
  const mIndividuais = metas?.metas_individuais ?? {};

  const rankingComMeta = useMemo(() => {
    const rows = data?.ranking_vendedores ?? [];
    return rows.map(r => {
      const meta = Object.entries(mIndividuais).find(
        ([k]) => k.trim().toLowerCase() === (r.Vendedor ?? '').trim().toLowerCase()
      )?.[1];
      return {
        ...r,
        _pct_meta: meta > 0 ? Math.round((r.valor_convertido ?? 0) / meta * 100) : null,
      };
    });
  }, [data, mIndividuais]);

  const canceladosVend = useMemo(
    () => data?.cancelados_por_vendedor ?? [],
    [data]
  );
  const rankingComCanc = useMemo(() => {
    const cancMap = Object.fromEntries(canceladosVend.map(r => [r.Vendedor, r.cancelados]));
    return rankingComMeta.map(r => ({ ...r, cancelados: cancMap[r.Vendedor] ?? 0 }));
  }, [rankingComMeta, canceladosVend]);

  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      Carregando dados de CRM…
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
        <p>Bot CRM está processando dados do banco…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  );

  const taxaConv   = data?.taxa_conversao_pct ?? 0;
  const deltaTaxa  = data?.delta_taxa_conv    ?? null;
  const taxaVariant = taxaConv >= 40 ? 'success' : taxaConv >= 25 ? 'warning' : 'error';

  return (
    <div className="p-6 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Performance Comercial</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* 4 KPI cards */}
      <div className="grid grid-cols-4 gap-3">
        <KpiCard
          label="Taxa de Conversão"
          value={pct(taxaConv)}
          sub={fmtDelta(deltaTaxa, 'pp')}
          variant={taxaVariant}
          topBorder="#1f6feb"
        />
        <KpiCard
          label="Clientes Inativos"
          value={String(data?.qtd_inativos ?? 0)}
          variant="warning"
          topBorder="#d29922"
        />
        <KpiCard
          label="Em Risco"
          value={String(data?.qtd_em_risco ?? 0)}
          variant="warning"
          topBorder="#da3633"
        />
        <KpiCard
          label="Ativos no Mês"
          value={String(data?.qtd_ativos_mes ?? 0)}
          variant="success"
          topBorder="#238636"
        />
      </div>

      {/* Ranking de Vendedores */}
      <div className="bg-card border border-card_border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
            Ranking de Vendedores
          </span>
          <div className="flex-1 h-px bg-card_border" />
          <span className="text-[9px] text-subtext">mês atual</span>
        </div>
        <DataTable columns={RANKING_COLS} rows={rankingComCanc} />
      </div>

      {/* Charts row */}
      <div className="flex gap-3 items-start">
        {/* Convertidos vs Cancelados */}
        <div className="flex-1 bg-card border border-card_border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Convertidos vs Cancelados
            </span>
            <div className="flex-1 h-px bg-card_border" />
          </div>
          <BarChart
            data={rankingComCanc.slice(0, 8)}
            xKey="Vendedor"
            bars={[
              { key: 'convertidos', label: 'Convertidos' },
              { key: 'cancelados',  label: 'Cancelados' },
            ]}
            stacked={false}
            height={200}
          />
        </div>

        {/* Evolução Semanal */}
        <div className="w-[42%] bg-card border border-card_border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Evolução Semanal
            </span>
            <div className="flex-1 h-px bg-card_border" />
          </div>
          <AreaChart
            data={data?.evolucao_semanal ?? []}
            xKey="semana"
            areas={[
              { key: 'propostas',   label: 'Propostas' },
              { key: 'convertidos', label: 'Convertidos' },
            ]}
            height={200}
          />
        </div>
      </div>

      {/* Top Clientes + Em Risco */}
      <div className="flex gap-3 items-start">
        <div className="flex-1 bg-card border border-card_border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Top Clientes do Mês
            </span>
            <div className="flex-1 h-px bg-card_border" />
          </div>
          <DataTable columns={TOP_COLS} rows={data?.top_clientes ?? []} />
        </div>

        <div className="flex-1 bg-card border border-card_border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
              Clientes em Risco
            </span>
            <div className="flex-1 h-px bg-card_border" />
          </div>
          <DataTable columns={RISCO_COLS} rows={(data?.clientes_risco ?? []).slice(0, 10)} />
        </div>
      </div>

      {/* Inativos com último vendedor */}
      <div className="bg-card border border-card_border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[10px] font-bold text-subtext uppercase tracking-widest">
            Clientes Inativos — Último Vendedor
          </span>
          <div className="flex-1 h-px bg-card_border" />
          <span className="text-[9px] text-subtext">{data?.inativos_lista?.length ?? 0} clientes</span>
        </div>
        <DataTable columns={INAT_COLS} rows={(data?.inativos_lista ?? []).slice(0, 50)} />
      </div>

    </div>
  );
}
