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
      <span style={{ fontSize: 11, fontWeight: 600, color: '#cbd5e1', textTransform: 'uppercase', letterSpacing: '1px' }}>
        {children}
      </span>
      <div style={{ flex: 1, height: 1, background: C.border }} />
      {right && <span style={{ fontSize: 10, color: C.sub }}>{right}</span>}
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
        const barWidth = Math.min(r._pct_meta, 100); // escala 1:1 — 80% meta = barra 80% larga
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
                  height: '100%', width: `${barWidth}%`,
                  background: barColor, borderRadius: 3, transition: 'width 0.3s',
                }} />
                <div style={{
                  position: 'absolute', top: 0, left: '80%',
                  width: 1.5, height: '100%', background: '#f1f5f9', opacity: 0.5,
                }} />
              </div>
              <span style={{ fontSize: 10, color: barColor, width: 32, textAlign: 'right' }}>
                {r._pct_meta.toFixed(0)}%
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
  { key: 'CodCli',         label: 'Código',        render: v => <span style={{ color: C.muted, fontFamily: 'monospace' }}>{v ?? '—'}</span> },
  { key: 'nome_cliente',   label: 'Cliente' },
  { key: 'dias_inativo',   label: 'Dias',           render: v => {
    const n = v ?? 0;
    return <span style={{ color: n >= 80 ? C.red : C.amber, fontWeight: 600 }}>{String(n)}</span>;
  }},
  { key: 'ultima_compra',  label: 'Última Compra',  render: v => fmtDate(v) },
  { key: 'ultimo_vendedor', label: 'Ult. Vendedor' },
];

const TOP_COLS = [
  { key: 'nome_cliente', label: 'Cliente' },
  { key: 'valor_mes',    label: 'Valor',   render: v => shortBrl(v) },
  { key: 'vendedor',     label: 'Vendedor' },
  { key: 'pedidos',      label: 'Pedidos', render: v => String(v ?? 0) },
];

const INAT_COLS = [
  { key: 'CodCli',                label: 'Código',         render: v => <span style={{ color: C.muted, fontFamily: 'monospace' }}>{v ?? '—'}</span> },
  { key: 'nome_cliente',          label: 'Cliente' },
  { key: 'dias_inativo',          label: 'Dias',           render: v => {
    const n = v ?? 0;
    return <span style={{ color: n > 180 ? C.red : C.amber, fontWeight: 600 }}>{String(n)}</span>;
  }},
  { key: 'ultima_compra',         label: 'Última Compra',  render: v => fmtDate(v) },
  { key: 'ultimo_vendedor',       label: 'Ult. Vendedor' },
  { key: 'faturamento_historico', label: 'Fat. Histórico', render: v => brl(v) },
];

const INAT_PAGE_SIZE  = 50;
const RISCO_PAGE_SIZE = 25;

const CTRL_STYLE = {
  background: '#0f172a', border: '1px solid #334155', borderRadius: 6,
  color: '#f1f5f9', fontSize: 11, padding: '5px 10px', outline: 'none',
};
const BTN_STYLE = {
  background: '#1e293b', border: '1px solid #334155', borderRadius: 4,
  color: '#94a3b8', cursor: 'pointer', fontSize: 12, padding: '3px 10px',
  transition: 'background 0.15s',
};

// ── Main component ────────────────────────────────────────────────
export default function CRM({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('crm', {}, refreshTrigger);
  const { metas } = useMetas();
  const mIndividuais = metas?.metas_individuais ?? {};

  // ── Inativos — filtros e paginação ───────────────────────────
  const [inatFiltroAno, setInatFiltroAno] = useState('');
  const [inatFiltroCod, setInatFiltroCod] = useState('');
  const [inatPage,      setInatPage]      = useState(0);

  const anosInat = useMemo(() => {
    const anos = new Set(
      (data?.inativos_lista ?? []).map(r => {
        const m = String(r.ultima_compra ?? '').match(/^(\d{4})/);
        return m ? m[1] : null;
      }).filter(Boolean)
    );
    return [...anos].sort().reverse();
  }, [data]);

  const inatFiltrados = useMemo(() => {
    const cod = inatFiltroCod.trim().toLowerCase();
    return (data?.inativos_lista ?? []).filter(r => {
      if (inatFiltroAno) {
        const m = String(r.ultima_compra ?? '').match(/^(\d{4})/);
        if (!m || m[1] !== inatFiltroAno) return false;
      }
      if (cod && !String(r.CodCli ?? '').toLowerCase().includes(cod)) return false;
      return true;
    });
  }, [data, inatFiltroAno, inatFiltroCod]);

  const inatTotalPages = Math.max(1, Math.ceil(inatFiltrados.length / INAT_PAGE_SIZE));
  const inatPageRows   = inatFiltrados.slice(inatPage * INAT_PAGE_SIZE, (inatPage + 1) * INAT_PAGE_SIZE);

  function setFiltroAno(v) { setInatFiltroAno(v); setInatPage(0); }
  function setFiltroCod(v) { setInatFiltroCod(v); setInatPage(0); }

  // ── Clientes em Risco — filtros e paginação ──────────────────
  // riscoFiltroMax: "até X dias" — mostra clientes com dias_inativo <= X
  // (do dia de hoje até X dias atrás = risco mais recente primeiro)
  const [riscoFiltroMax, setRiscoFiltroMax] = useState('');
  const [riscoFiltroCod, setRiscoFiltroCod] = useState('');
  const [riscoPage,      setRiscoPage]      = useState(0);

  const riscoFiltrados = useMemo(() => {
    const cod = riscoFiltroCod.trim().toLowerCase();
    const max = riscoFiltroMax ? parseInt(riscoFiltroMax, 10) : 0;
    return (data?.clientes_risco ?? []).filter(r => {
      if (max > 0 && (r.dias_inativo ?? 0) > max) return false;
      if (cod && !String(r.CodCli ?? '').toLowerCase().includes(cod)) return false;
      return true;
    });
  }, [data, riscoFiltroMax, riscoFiltroCod]);

  const riscoTotalPages = Math.max(1, Math.ceil(riscoFiltrados.length / RISCO_PAGE_SIZE));
  const riscoPageRows   = riscoFiltrados.slice(riscoPage * RISCO_PAGE_SIZE, (riscoPage + 1) * RISCO_PAGE_SIZE);

  function setRiscoMax(v) { setRiscoFiltroMax(v); setRiscoPage(0); }
  function setRiscoCod(v) { setRiscoFiltroCod(v); setRiscoPage(0); }

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
          <div style={{ fontSize: 11, color: C.muted, marginTop: 4 }}>60–89 dias sem compra</div>
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
            xFormatter={name => (name ?? '').split(' ')[0]}
            colors={[C.cyan]}
            height={200}
          />
        </Card>

        <Card>
          <SectionLabel>% de Meta por Vendedor</SectionLabel>
          <BulletBars rows={rankingComMeta.slice(0, 8)} metas={mIndividuais} />
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

        {/* Left: Top Clientes */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card>
            <SectionLabel>Top Clientes do Mês</SectionLabel>
            <DataTable columns={TOP_COLS} rows={data?.top_clientes ?? []} />
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
              xFormatter={s => { const m = String(s ?? '').match(/\d{4}-(\d{2})-(\d{2})/); return m ? `${m[2]}/${m[1]}` : (s ?? ''); }}
              colors={[C.cyan, C.green]}
              height={180}
            />
          </Card>
        </div>

      </div>

      {/* ── Clientes em Risco (full width) ───────────────────── */}
      <Card>
        <SectionLabel right={`${riscoFiltrados.length} de ${data?.clientes_risco?.length ?? 0} clientes`}>
          Clientes em Risco
        </SectionLabel>

        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <select
            value={riscoFiltroMax}
            onChange={e => setRiscoMax(e.target.value)}
            style={CTRL_STYLE}
          >
            <option value="">Todos os dias</option>
            <option value="40">Até 40 dias</option>
            <option value="50">Até 50 dias</option>
            <option value="60">Até 60 dias</option>
            <option value="70">Até 70 dias</option>
            <option value="80">Até 80 dias</option>
            <option value="90">Até 90 dias</option>
          </select>
          <input
            type="text"
            placeholder="Filtrar por código..."
            value={riscoFiltroCod}
            onChange={e => setRiscoCod(e.target.value)}
            style={{ ...CTRL_STYLE, width: 160 }}
          />
          {(riscoFiltroMax || riscoFiltroCod) && (
            <button
              onClick={() => { setRiscoMax(''); setRiscoCod(''); }}
              style={{ ...BTN_STYLE, color: C.amber }}
            >
              Limpar filtros
            </button>
          )}
        </div>

        {riscoPageRows.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 0', color: C.muted, fontSize: 13 }}>
            Nenhum cliente encontrado com estes filtros.
          </div>
        ) : (
          <DataTable columns={RISCO_COLS} rows={riscoPageRows} />
        )}

        {riscoTotalPages > 1 && (
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center', alignItems: 'center', marginTop: 14 }}>
            <button style={{ ...BTN_STYLE, opacity: riscoPage === 0 ? 0.35 : 1 }}
              disabled={riscoPage === 0} onClick={() => setRiscoPage(0)}>«</button>
            <button style={{ ...BTN_STYLE, opacity: riscoPage === 0 ? 0.35 : 1 }}
              disabled={riscoPage === 0} onClick={() => setRiscoPage(p => p - 1)}>‹</button>
            <span style={{ fontSize: 11, color: C.sub, padding: '0 8px' }}>
              {riscoPage + 1} / {riscoTotalPages}
              <span style={{ color: C.muted, marginLeft: 8 }}>({riscoFiltrados.length} registros)</span>
            </span>
            <button style={{ ...BTN_STYLE, opacity: riscoPage >= riscoTotalPages - 1 ? 0.35 : 1 }}
              disabled={riscoPage >= riscoTotalPages - 1} onClick={() => setRiscoPage(p => p + 1)}>›</button>
            <button style={{ ...BTN_STYLE, opacity: riscoPage >= riscoTotalPages - 1 ? 0.35 : 1 }}
              disabled={riscoPage >= riscoTotalPages - 1} onClick={() => setRiscoPage(riscoTotalPages - 1)}>»</button>
          </div>
        )}
      </Card>

      {/* ── Clientes Inativos (full width) ───────────────────── */}
      <Card>
        <SectionLabel right={`${inatFiltrados.length} de ${data?.inativos_lista?.length ?? 0} clientes`}>
          Clientes Inativos — Último Vendedor
        </SectionLabel>

        {/* Barra de filtros */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <select
            value={inatFiltroAno}
            onChange={e => setFiltroAno(e.target.value)}
            style={CTRL_STYLE}
          >
            <option value="">Todos os anos</option>
            {anosInat.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <input
            type="text"
            placeholder="Filtrar por código..."
            value={inatFiltroCod}
            onChange={e => setFiltroCod(e.target.value)}
            style={{ ...CTRL_STYLE, width: 160 }}
          />
          {(inatFiltroAno || inatFiltroCod) && (
            <button
              onClick={() => { setFiltroAno(''); setFiltroCod(''); }}
              style={{ ...BTN_STYLE, color: C.amber }}
            >
              Limpar filtros
            </button>
          )}
        </div>

        <DataTable columns={INAT_COLS} rows={inatPageRows} />

        {/* Paginação */}
        {inatTotalPages > 1 && (
          <div style={{ display: 'flex', gap: 6, justifyContent: 'center', alignItems: 'center', marginTop: 14 }}>
            <button style={{ ...BTN_STYLE, opacity: inatPage === 0 ? 0.35 : 1 }}
              disabled={inatPage === 0} onClick={() => setInatPage(0)}>«</button>
            <button style={{ ...BTN_STYLE, opacity: inatPage === 0 ? 0.35 : 1 }}
              disabled={inatPage === 0} onClick={() => setInatPage(p => p - 1)}>‹</button>
            <span style={{ fontSize: 11, color: C.sub, padding: '0 8px' }}>
              {inatPage + 1} / {inatTotalPages}
              <span style={{ color: C.muted, marginLeft: 8 }}>({inatFiltrados.length} registros)</span>
            </span>
            <button style={{ ...BTN_STYLE, opacity: inatPage >= inatTotalPages - 1 ? 0.35 : 1 }}
              disabled={inatPage >= inatTotalPages - 1} onClick={() => setInatPage(p => p + 1)}>›</button>
            <button style={{ ...BTN_STYLE, opacity: inatPage >= inatTotalPages - 1 ? 0.35 : 1 }}
              disabled={inatPage >= inatTotalPages - 1} onClick={() => setInatPage(inatTotalPages - 1)}>»</button>
          </div>
        )}
      </Card>

    </div>
  );
}
