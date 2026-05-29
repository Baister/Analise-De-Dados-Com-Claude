import { useMemo, useState } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import { useMetas } from '../hooks/useMetas';
import BarChart from '../charts/BarChart';
import AreaChart from '../charts/AreaChart';
import DataTable from '../components/DataTable';
import { BarChart as RC, Bar, XAxis, YAxis, Tooltip as RCTooltip, Cell, ResponsiveContainer, CartesianGrid, LabelList } from 'recharts';
import { brl, shortBrl, pct, fmtDate } from '../utils/format';

// ── Color tokens ──────────────────────────────────────────────────
const C = {
  page:   '#0f172a',
  card:   '#1e293b',
  border: '#334155',
  cyan:   '#06b6d4',
  green:  '#22c55e',
  amber:  '#f59e0b',
  red:    '#ef4444',
  text:   '#f1f5f9',
  sub:    '#94a3b8',
  muted:  '#64748b',
};

// ── Mini components ───────────────────────────────────────────────
function SectionLabel({ children, right }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
      <span style={{ fontSize: 10, color: C.muted, textTransform: 'uppercase', letterSpacing: '1px' }}>
        {children}
      </span>
      <div style={{ flex: 1, height: 1, background: C.border }} />
      {right && <span style={{ fontSize: 9, color: C.muted }}>{right}</span>}
    </div>
  );
}

function Card({ children, style }) {
  return (
    <div style={{
      background: C.card,
      border: `1px solid ${C.border}`,
      borderRadius: 8,
      padding: 16,
      ...style,
    }}>
      {children}
    </div>
  );
}

function DeltaBadge({ delta, unit = '' }) {
  if (delta === 0 || delta == null) return null;
  const pos = delta > 0;
  return (
    <div style={{
      background: pos ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
      color: pos ? C.green : C.red,
      borderRadius: 4,
      padding: '2px 8px',
      fontSize: 11,
      marginTop: 6,
      display: 'inline-block',
    }}>
      {pos ? '↑ +' : '↓ '}{Math.abs(delta)}{unit} vs mês ant.
    </div>
  );
}

// ── Histograma de inatividade — cores por faixa ───────────────────
const HIST_COLORS = ['#f59e0b', '#f97316', '#ef4444', '#7f1d1d'];

// ── Bullet Bars — % de Meta por Vendedor ─────────────────────────
function BulletBars({ rows, metas }) {
  const [hovered, setHovered] = useState(null);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, position: 'relative' }}>
      {rows.filter(r => r._pct_meta != null).map((r, i) => {
        const pct100 = Math.min(r._pct_meta, 120);
        const barColor = r._pct_meta >= 80 ? C.green : r._pct_meta >= 60 ? C.amber : C.red;
        const metaVal = Object.entries(metas).find(
          ([k]) => k.trim().toLowerCase() === (r.Vendedor ?? '').trim().toLowerCase()
        )?.[1] ?? 0;
        return (
          <div key={r.Vendedor} style={{ position: 'relative' }}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                fontSize: 11, color: C.sub, width: 80,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {(r.Vendedor ?? '').split(' ')[0]}
              </span>
              <div style={{
                flex: 1, height: 12, background: '#0f172a',
                borderRadius: 3, position: 'relative', overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%', width: `${pct100 / 1.2}%`,
                  background: barColor, borderRadius: 3, transition: 'width 0.3s',
                }} />
                <div style={{
                  position: 'absolute', top: 0, left: '66.7%',
                  width: 1.5, height: '100%', background: '#f1f5f9', opacity: 0.5,
                }} />
              </div>
              <span style={{ fontSize: 10, color: barColor, width: 32, textAlign: 'right' }}>
                {pct100.toFixed(0)}%
              </span>
            </div>
            {hovered === i && (
              <div style={{
                position: 'absolute', left: 88, top: -8, zIndex: 10,
                background: '#1c2128', border: '1px solid #30363d',
                borderRadius: 6, fontSize: 11, padding: '8px 12px', color: '#e6edf3',
                pointerEvents: 'none', whiteSpace: 'nowrap',
              }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.Vendedor}</div>
                <div style={{ color: '#8b949e' }}>
                  Convertido: <span style={{ color: '#e6edf3' }}>{brl(r.valor_convertido ?? 0)}</span>
                </div>
                <div style={{ color: '#8b949e' }}>
                  Meta: <span style={{ color: '#e6edf3' }}>{brl(metaVal)}</span>
                </div>
                <div style={{ color: '#8b949e' }}>
                  Atingimento: <span style={{ color: barColor }}>{r._pct_meta}%</span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Column definitions ────────────────────────────────────────────
const RANKING_COLS = [
  { key: 'Vendedor',         label: 'Vendedor' },
  { key: 'propostas',        label: 'Propostas',  render: v => String(v ?? 0) },
  { key: 'convertidos',      label: 'Conv.',      render: v => String(v ?? 0) },
  { key: 'taxa_conv',        label: 'Taxa',       render: v => {
    const n = v ?? 0;
    const color = n >= 40 ? C.green : n >= 25 ? C.amber : C.red;
    return <span style={{ color, fontWeight: 600 }}>{pct(n)}</span>;
  }},
  { key: 'valor_convertido', label: 'Valor',      render: v => shortBrl(v) },
  { key: 'ticket_medio',     label: 'Ticket',     render: v => shortBrl(v) },
  { key: 'cancelados',       label: 'Canc.',      render: v => {
    const n = v ?? 0;
    return <span style={{ color: n > 0 ? C.red : C.muted }}>{String(n)}</span>;
  }},
  { key: '_pct_meta',        label: '% Meta',     render: v => {
    if (v == null) return <span style={{ color: C.muted }}>—</span>;
    const [color, bg] = v >= 80
      ? [C.cyan,  'rgba(6,182,212,0.15)']
      : v >= 60
        ? [C.amber, 'rgba(245,158,11,0.15)']
        : [C.red,   'rgba(239,68,68,0.15)'];
    return (
      <span style={{ background: bg, color, borderRadius: 4, padding: '1px 6px', fontSize: 11 }}>
        {pct(v)}
      </span>
    );
  }},
];

const RISCO_COLS = [
  { key: 'nome_cliente',    label: 'Cliente' },
  { key: 'dias_inativo',   label: 'Dias',          render: v => (
    <span style={{ color: C.amber, fontWeight: 600 }}>{String(v ?? 0)}</span>
  )},
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
  { key: 'dias_inativo',          label: 'Dias',           render: v => {
    const n = v ?? 0;
    return <span style={{ color: n > 180 ? C.red : C.amber, fontWeight: 600 }}>{String(n)}</span>;
  }},
  { key: 'ultima_compra',         label: 'Última Compra',  render: v => fmtDate(v) },
  { key: 'ultimo_vendedor',       label: 'Ult. Vendedor' },
  { key: 'faturamento_historico', label: 'Fat. Histórico', render: v => brl(v) },
];

// ── Main component ────────────────────────────────────────────────
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

  // ── Guards ────────────────────────────────────────────────────
  if (loading && !data) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 256, color: C.muted, fontSize: 14 }}>
      Carregando dados de CRM…
    </div>
  );
  if (error && !data) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 256, color: C.red, fontSize: 14 }}>
      Erro ao carregar dados: {error}
    </div>
  );
  if (isEmpty) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 256, color: C.muted, fontSize: 14 }}>
      <div style={{ textAlign: 'center' }}>
        <p>Bot CRM está processando dados do banco…</p>
        <p style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  );

  // ── KPI values ────────────────────────────────────────────────
  const taxaConv  = data?.taxa_conversao_pct ?? 0;
  const deltaTaxa = data?.delta_taxa_conv    ?? null;
  const pipeline  = data?.valor_orcado       ?? 0;
  const deltaPipe = data?.delta_valor_orcado ?? null;
  const qtdInat   = data?.qtd_inativos       ?? 0;
  const qtdRisco  = data?.qtd_em_risco       ?? 0;
  const taxaColor = taxaConv >= 40 ? C.green : taxaConv >= 25 ? C.amber : C.red;

  return (
    <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* ── Header ───────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: C.text, margin: 0 }}>
          Performance Comercial
        </h1>
        {data?.ultimo_update && (
          <span style={{ fontSize: 11, color: C.muted }}>Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* ── 4 KPI cards ──────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>

        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.cyan}`, borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 10, color: C.muted, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: 4 }}>Taxa de Conversão</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: taxaColor }}>{pct(taxaConv)}</div>
          <DeltaBadge delta={deltaTaxa} unit="pp" />
        </div>

        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.red}`, borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 10, color: C.muted, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: 4 }}>Clientes Inativos</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.red }}>{qtdInat}</div>
          <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>sem compra &gt;90 dias</div>
        </div>

        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.amber}`, borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 10, color: C.muted, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: 4 }}>Em Risco</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.amber }}>{qtdRisco}</div>
          <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>60–90 dias sem compra</div>
        </div>

        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.green}`, borderRadius: 8, padding: '14px 16px' }}>
          <div style={{ fontSize: 10, color: C.muted, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: 4 }}>Pipeline R$</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.text }}>{shortBrl(pipeline)}</div>
          <DeltaBadge delta={deltaPipe != null ? Math.round(deltaPipe / 1000) : null} unit="k" />
        </div>

      </div>

      {/* ── Ranking de Vendedores (full width) ───────────────── */}
      <Card>
        <SectionLabel right="mês atual">Ranking de Vendedores</SectionLabel>
        <DataTable columns={RANKING_COLS} rows={rankingComCanc} />
      </Card>

      {/* ── 3 gráficos analíticos ────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>

        <Card>
          <SectionLabel>Ticket Médio por Vendedor</SectionLabel>
          <BarChart
            data={rankingComCanc.slice(0, 8)}
            xKey="Vendedor"
            bars={[{ key: 'ticket_medio', label: 'Ticket Médio', formatter: shortBrl }]}
            tooltipExtra={[{ key: 'convertidos', label: 'Vendas' }]}
            colors={[C.cyan]}
            height={200}
          />
        </Card>

        <Card>
          <SectionLabel>% de Meta por Vendedor</SectionLabel>
          <BulletBars rows={rankingComMeta} metas={mIndividuais} />
        </Card>

        <Card>
          <SectionLabel>Faixas de Inatividade</SectionLabel>
          <ResponsiveContainer width="100%" height={200}>
            <RC
              data={data?.faixas_inatividade ?? []}
              margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
              <XAxis dataKey="faixa" tick={{ fill: C.sub, fontSize: 10 }} />
              <YAxis tick={{ fill: C.sub, fontSize: 10 }} allowDecimals={false} />
              <RCTooltip
                contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#e6edf3' }}
                itemStyle={{ color: '#8b949e' }}
              />
              <Bar dataKey="qtd" name="Clientes" radius={[3, 3, 0, 0]}>
                {(data?.faixas_inatividade ?? []).map((_, i) => (
                  <Cell key={i} fill={HIST_COLORS[i] ?? '#ef4444'} />
                ))}
                <LabelList dataKey="qtd" position="top" style={{ fill: '#f1f5f9', fontSize: 11, fontWeight: 700 }} />
              </Bar>
            </RC>
          </ResponsiveContainer>
        </Card>

      </div>

      {/* ── Middle grid: 55/45 ───────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '55fr 45fr', gap: 12 }}>

        {/* Left: Top Clientes + Em Risco */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card>
            <SectionLabel>Top Clientes do Mês</SectionLabel>
            <DataTable columns={TOP_COLS} rows={data?.top_clientes ?? []} />
          </Card>
          <Card>
            <SectionLabel>Clientes em Risco</SectionLabel>
            <DataTable columns={RISCO_COLS} rows={(data?.clientes_risco ?? []).slice(0, 10)} />
          </Card>
        </div>

        {/* Right: Charts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card>
            <SectionLabel>Convertidos vs Cancelados</SectionLabel>
            <BarChart
              data={rankingComCanc.slice(0, 8)}
              xKey="Vendedor"
              bars={[
                { key: 'convertidos', label: 'Convertidos' },
                { key: 'cancelados',  label: 'Cancelados'  },
              ]}
              colors={[C.green, C.red]}
              stacked={false}
              height={180}
            />
          </Card>
          <Card>
            <SectionLabel>Evolução Semanal</SectionLabel>
            <AreaChart
              data={data?.evolucao_semanal ?? []}
              xKey="inicio_semana"
              areas={[
                { key: 'propostas',   label: 'Propostas'   },
                { key: 'convertidos', label: 'Convertidos' },
              ]}
              colors={[C.cyan, C.green]}
              height={180}
            />
          </Card>
        </div>

      </div>

      {/* ── Clientes Inativos (full width) ───────────────────── */}
      <Card>
        <SectionLabel right={`${data?.inativos_lista?.length ?? 0} clientes`}>
          Clientes Inativos — Último Vendedor
        </SectionLabel>
        <DataTable columns={INAT_COLS} rows={(data?.inativos_lista ?? []).slice(0, 50)} />
      </Card>

    </div>
  );
}
