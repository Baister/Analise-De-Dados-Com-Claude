import { useState, useMemo } from 'react';
import { useDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, fmtDate } from '../utils/format';

const AZUL = '#1f6feb', VERDE = '#238636', AMBAR = '#d29922', VERM = '#da3633', ROXO = '#a371f7';
const SEG_COLORS = [VERDE, AMBAR, '#f97316', VERM];
const ABC_COLOR = { A: VERDE, B: AMBAR, C: VERM };

const fmtInt = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }));

function SectionLabel({ children, first }) {
  return (
    <p className="text-[10px] text-subtext uppercase mb-[7px]"
      style={{ letterSpacing: '1px', marginTop: first ? 0 : 18 }}>{children}</p>
  );
}
function Card({ children, className = '' }) {
  return <div className={`bg-card border border-card_border rounded-lg p-4 ${className}`}>{children}</div>;
}
function CardTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>{children}</p>
      {right && <span className="text-[9px] text-subtext opacity-70">{right}</span>}
    </div>
  );
}

const diasBadge = d => {
  const [c, bg] = d <= 30 ? ['#4ade80', 'rgba(35,134,54,0.15)']
    : d <= 60 ? ['#fbbf24', 'rgba(210,153,34,0.15)']
    : d <= 90 ? ['#fb923c', 'rgba(249,115,22,0.15)'] : ['#f87171', 'rgba(218,54,51,0.15)'];
  return <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 8px', borderRadius: 9999, background: bg, color: c }}>{d}d</span>;
};

const COLS = [
  { key: 'CodCli', label: 'Cód.', render: v => <span className="text-subtext" style={{ fontFamily: 'monospace' }}>{v}</span> },
  { key: 'nome', label: 'Cliente' },
  { key: 'abc', label: 'ABC', render: v => {
      const c = ABC_COLOR[v] || '#8b949e';
      return <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 7px', borderRadius: 9999, background: `${c}26`, color: c }}>{v}</span>;
    } },
  { key: 'receita', label: 'Receita 12m', align: 'right', render: brl },
  { key: 'pedidos', label: 'Pedidos', align: 'right', render: fmtInt },
  { key: 'ticket',  label: 'Ticket',  align: 'right', render: brl },
  { key: 'ultima_compra', label: 'Última Compra', render: v => fmtDate(v) },
  { key: 'dias', label: 'Recência', render: v => diasBadge(v ?? 0) },
];

export default function ClienteComportamento({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useDados('cliente_comportamento', refreshTrigger);
  const [busca, setBusca] = useState('');

  const kpis = data?.kpis ?? {};
  const topFiltrado = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const rows = data?.top_clientes ?? [];
    if (!q) return rows;
    return rows.filter(r => String(r.nome ?? '').toLowerCase().includes(q) ||
                            String(r.CodCli ?? '').toLowerCase().includes(q));
  }, [data, busca]);

  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">Carregando análise da carteira…</div>
  );
  if (error && !data) return (
    <div className="flex items-center justify-center h-64 text-accent_red text-sm">Erro ao carregar dados: {error}</div>
  );
  if (isEmpty) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      <div className="text-center space-y-1">
        <p>Bot Clientes está processando a carteira…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  );

  return (
    <div className="p-4">
      <div className="flex items-end justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-text_main text-lg font-bold leading-tight">Clientes — Carteira</h1>
          <p className="text-subtext text-[11px]">
            Análise agregada de todos os clientes (12 meses) · para o perfil individual use a aba <b>Cliente</b>
            {data?.ultimo_update && <> · Atualizado {data.ultimo_update}</>}
          </p>
        </div>
      </div>

      <SectionLabel first>Visão Geral da Carteira (12 meses)</SectionLabel>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
        <KpiCard label="Clientes Compradores" value={fmtInt(kpis.clientes_12m)}
          sub="compraram nos últimos 12m" topBorder={AZUL} gradient="rgba(31,111,235,0.10)" />
        <KpiCard label="Ativos no Mês" value={fmtInt(kpis.ativos_mes)}
          sub="compraram no mês atual" topBorder={VERDE} />
        <KpiCard label="Novos no Mês" value={fmtInt(kpis.novos_mes)}
          sub="1ª compra da história" variant="success" topBorder={VERDE} />
        <KpiCard label="Receita 12m" value={brl(kpis.receita_12m)}
          sub="vendas líquidas" topBorder={AZUL} />
        <KpiCard label="Ticket Médio" value={brl(kpis.ticket_medio)}
          sub="por pedido, na carteira" topBorder={ROXO} valueColor="#c084fc" />
        <KpiCard label="Concentração Top 10" value={kpis.top10_pct != null ? `${String(kpis.top10_pct).replace('.', ',')}%` : '—'}
          sub="% da receita nos 10 maiores"
          valueColor={(kpis.top10_pct ?? 0) > 50 ? '#f87171' : (kpis.top10_pct ?? 0) > 30 ? '#fbbf24' : '#4ade80'}
          topBorder={(kpis.top10_pct ?? 0) > 50 ? VERM : (kpis.top10_pct ?? 0) > 30 ? AMBAR : VERDE} />
      </div>

      <SectionLabel>Saúde da Carteira</SectionLabel>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <Card>
          <CardTitle right="pela última compra">Segmentação por Recência</CardTitle>
          <PieChart
            data={data?.segmentacao ?? []} nameKey="faixa" valueKey="qtd"
            showValue formatter={fmtInt} colors={SEG_COLORS} height={210}
            tooltipContext={{
              title: 'Clientes',
              formula: 'Faixas pela data da última compra (iguais à aba Cliente)',
              extra: [{ key: 'receita', label: 'Receita 12m', formatter: brl }],
            }}
          />
        </Card>
        <Card>
          <CardTitle right="por receita 12m · A=80% · B=15% · C=5%">Curva ABC de Clientes</CardTitle>
          <div className="flex flex-col gap-2.5 pt-1">
            {(data?.abc_resumo ?? []).map(a => (
              <div key={a.classe}
                className="bg-bg border border-card_border rounded-lg px-4 py-2.5 flex items-center gap-3"
                style={{ borderLeft: `3px solid ${ABC_COLOR[a.classe]}` }}>
                <span className="text-xl font-bold" style={{ color: ABC_COLOR[a.classe] }}>{a.classe}</span>
                <div className="flex-1">
                  <p className="text-text_main text-sm font-semibold leading-tight">
                    {fmtInt(a.clientes)} clientes
                    <span className="text-subtext font-normal"> · {String(a.pct_receita).replace('.', ',')}% da receita</span>
                  </p>
                  <p className="text-subtext text-[10px]">{brl(a.receita)}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <SectionLabel>Evolução — Clientes Ativos por Mês</SectionLabel>
      <Card>
        <BarChart
          data={data?.evolucao ?? []} xKey="mes" height={220}
          bars={[{ key: 'ativos', label: 'Clientes ativos', formatter: fmtInt }]}
          colors={[AZUL]}
          tooltipExtra={[{ key: 'receita', label: 'Receita', formatter: brl }]}
        />
      </Card>

      <SectionLabel>Top Clientes da Carteira</SectionLabel>
      <Card>
        <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
          <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>
            Top 50 por receita (12 meses)
          </p>
          <input type="text" placeholder="Buscar nome ou código…" value={busca}
            onChange={e => setBusca(e.target.value)}
            className="w-56 px-3 py-1.5 text-xs bg-bg border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent" />
        </div>
        {topFiltrado.length === 0
          ? <p className="text-subtext text-xs text-center py-6">Nenhum cliente encontrado.</p>
          : <DataTable columns={COLS} rows={topFiltrado} />}
        <p className="text-subtext text-[10px] mt-2 opacity-70">
          Para mergulhar num cliente específico, copie o código e abra na aba <b>Cliente</b> (perfil 360º).
        </p>
      </Card>
    </div>
  );
}
