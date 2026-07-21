import { useMemo, useState, useEffect } from 'react';
import { useFilteredDados } from '../hooks/useApi';
import { useMetas } from '../hooks/useMetas';
import KpiCard from '../components/KpiCard';
import BarChart from '../charts/BarChart';
import AreaChart from '../charts/AreaChart';
import DataTable from '../components/DataTable';
import { BarChart as RC, Bar, XAxis, YAxis, Tooltip as RCTooltip, Cell, ResponsiveContainer, CartesianGrid, LabelList } from 'recharts';
import { brl, shortBrl, pct, fmtDate } from '../utils/format';

// ── Paleta da casa (mesma de Dashboard/Estoque/Imposto) ───────────
const AZUL  = '#1f6feb';
const VERDE = '#238636';
const AMBAR = '#d29922';
const VERM  = '#da3633';
const ROXO  = '#a371f7';
const HIST_COLORS = ['#d29922', '#f97316', '#da3633', '#7f1d1d'];

const fmtInt = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }));

function SectionLabel({ children, first }) {
  return (
    <p className="text-[10px] text-subtext uppercase mb-[7px]"
      style={{ letterSpacing: '1px', marginTop: first ? 0 : 18 }}>
      {children}
    </p>
  );
}

function Card({ children, className = '' }) {
  return (
    <div className={`bg-card border border-card_border rounded-lg p-4 ${className}`}>
      {children}
    </div>
  );
}

function CardTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>{children}</p>
      {right && <span className="text-[9px] text-subtext opacity-70">{right}</span>}
    </div>
  );
}

// ── Funil do mês — barras horizontais proporcionais ───────────────
const FUNIL_COLORS = { 'Em Negociação': AMBAR, 'Fechadas': VERDE, 'Faturadas': AZUL };
function FunnelBars({ etapas }) {
  if (!etapas?.length) return <p className="text-subtext text-sm text-center py-6">Sem dados</p>;
  return (
    <div className="flex flex-col gap-2.5 py-1">
      {etapas.map(e => {
        const cor = FUNIL_COLORS[e.etapa] || '#8b949e';
        return (
          <div key={e.etapa}>
            <div className="flex justify-between text-[11px] mb-1">
              <span className="text-text_main">{e.etapa}</span>
              <span className="text-subtext">
                <b className="text-text_main">{fmtInt(e.qtd)}</b> · {pct(e.pct ?? 0, 1)}
              </span>
            </div>
            <div className="h-4 rounded bg-progress_bg overflow-hidden">
              <div style={{
                width: `${Math.max(Math.min(e.pct ?? 0, 100), 2)}%`, height: '100%',
                background: cor, borderRadius: 4, transition: 'width 0.3s',
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Bullet Bars — % de Meta por Vendedor (escala 1:1, traço em 80%) ─
function BulletBars({ rows, metas }) {
  const [hovered, setHovered] = useState(null);
  const comMeta = rows.filter(r => r._pct_meta != null);
  if (!comMeta.length) return <p className="text-subtext text-sm text-center py-6">Sem metas individuais configuradas</p>;
  return (
    <div className="flex flex-col gap-2 relative">
      {comMeta.map((r, i) => {
        const barWidth = Math.min(r._pct_meta, 100);
        const barColor = r._pct_meta >= 80 ? VERDE : r._pct_meta >= 60 ? AMBAR : VERM;
        const metaVal = Object.entries(metas).find(
          ([k]) => k.trim().toLowerCase() === (r.Vendedor ?? '').trim().toLowerCase()
        )?.[1] ?? 0;
        return (
          <div key={r.Vendedor} className="relative"
            onMouseEnter={() => setHovered(i)} onMouseLeave={() => setHovered(null)}>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-subtext w-20 whitespace-nowrap overflow-hidden text-ellipsis">
                {(r.Vendedor ?? '').split(' ')[0]}
              </span>
              <div className="flex-1 h-3 rounded bg-progress_bg relative overflow-hidden">
                <div style={{ height: '100%', width: `${barWidth}%`, background: barColor, borderRadius: 3, transition: 'width 0.3s' }} />
                <div style={{ position: 'absolute', top: 0, left: '80%', width: 1.5, height: '100%', background: '#e6edf3', opacity: 0.5 }} />
              </div>
              <span className="text-[10px] w-8 text-right" style={{ color: barColor }}>
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
                <div style={{ color: '#8b949e' }}>Convertido: <span style={{ color: '#e6edf3' }}>{brl(r.valor_convertido ?? 0)}</span></div>
                <div style={{ color: '#8b949e' }}>Meta: <span style={{ color: '#e6edf3' }}>{brl(metaVal)}</span></div>
                <div style={{ color: '#8b949e' }}>Atingimento: <span style={{ color: barColor }}>{r._pct_meta}%</span></div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Colunas ────────────────────────────────────────────────────────
const mono = v => <span className="text-subtext" style={{ fontFamily: 'monospace' }}>{v ?? '—'}</span>;

const RANKING_COLS = [
  { key: 'Vendedor',         label: 'Vendedor' },
  { key: 'propostas',        label: 'Propostas', align: 'right', render: v => String(v ?? 0) },
  { key: 'convertidos',      label: 'Conv.',     align: 'right', render: v => String(v ?? 0) },
  { key: 'taxa_conv',        label: 'Taxa', align: 'right', render: v => {
    const n = v ?? 0;
    const color = n >= 40 ? '#4ade80' : n >= 25 ? '#fbbf24' : '#f87171';
    return <span style={{ color, fontWeight: 600 }}>{pct(n)}</span>;
  }},
  { key: 'valor_convertido', label: 'Valor',  align: 'right', render: v => shortBrl(v) },
  { key: 'ticket_medio',     label: 'Ticket', align: 'right', render: v => shortBrl(v) },
  { key: 'cancelados',       label: 'Canc.',  align: 'right', render: v => {
    const n = v ?? 0;
    return <span style={{ color: n > 0 ? '#f87171' : '#8b949e' }}>{String(n)}</span>;
  }},
  { key: '_pct_meta', label: '% Meta', render: v => {
    if (v == null) return <span className="opacity-40">—</span>;
    const [color, bg] = v >= 80 ? ['#4ade80', 'rgba(35,134,54,0.15)']
      : v >= 60 ? ['#fbbf24', 'rgba(210,153,34,0.15)'] : ['#f87171', 'rgba(218,54,51,0.15)'];
    return <span style={{ background: bg, color, borderRadius: 4, padding: '1px 6px', fontSize: 11 }}>{pct(v)}</span>;
  }},
];

const RISCO_COLS = [
  { key: 'CodCli',       label: 'Código', render: mono },
  { key: 'nome_cliente', label: 'Cliente' },
  { key: 'dias_inativo', label: 'Dias', align: 'right', render: v => {
    const n = v ?? 0;
    return <span style={{ color: n >= 80 ? '#f87171' : '#fbbf24', fontWeight: 600 }}>{String(n)}</span>;
  }},
  { key: 'ultima_compra',   label: 'Última Compra', render: v => fmtDate(v) },
  { key: 'ultimo_vendedor', label: 'Ult. Vendedor' },
];

const TOP_COLS = [
  { key: 'nome_cliente', label: 'Cliente' },
  { key: 'valor_mes',    label: 'Valor', align: 'right', render: v => shortBrl(v) },
  { key: 'vendedor',     label: 'Vendedor' },
  { key: 'pedidos',      label: 'Pedidos', align: 'right', render: v => String(v ?? 0) },
];

const NOVOS_COLS = [
  { key: 'CodCli',          label: 'Código', render: mono },
  { key: 'nome_cliente',    label: 'Cliente' },
  { key: 'vendedor',        label: 'Vendedor' },
  { key: 'primeira_compra', label: '1ª Compra', render: v => fmtDate(v) },
  { key: 'valor_mes',       label: 'Valor', align: 'right', render: v => brl(v) },
];

const ORC_COLS = [
  { key: 'NrOrcPedVnd', label: 'Orçamento', render: mono },
  { key: 'cliente',     label: 'Cliente' },
  { key: 'vendedor',    label: 'Vendedor' },
  { key: 'DtOrcPedVnd', label: 'Data', render: v => fmtDate(v) },
  { key: 'dias_aberto', label: 'Aberto há', render: v => {
    const n = v ?? 0;
    const [color, bg] = n <= 7 ? ['#4ade80', 'rgba(35,134,54,0.15)']
      : n <= 30 ? ['#fbbf24', 'rgba(210,153,34,0.15)'] : ['#f87171', 'rgba(218,54,51,0.15)'];
    return <span style={{ background: bg, color, borderRadius: 9999, padding: '1px 8px', fontSize: 10, fontWeight: 600, whiteSpace: 'nowrap' }}>{n} dias</span>;
  }},
  { key: 'valor', label: 'Valor', align: 'right', render: v => brl(v) },
];

const INAT_COLS = [
  { key: 'CodCli',       label: 'Código', render: mono },
  { key: 'nome_cliente', label: 'Cliente' },
  { key: 'dias_inativo', label: 'Dias', align: 'right', render: v => {
    const n = v ?? 0;
    return <span style={{ color: n > 180 ? '#f87171' : '#fbbf24', fontWeight: 600 }}>{String(n)}</span>;
  }},
  { key: 'ultima_compra',         label: 'Última Compra', render: v => fmtDate(v) },
  { key: 'ultimo_vendedor',       label: 'Ult. Vendedor' },
  { key: 'faturamento_historico', label: 'Fat. Histórico', align: 'right', render: v => brl(v) },
];

const INAT_PAGE_SIZE  = 50;
const RISCO_PAGE_SIZE = 25;
const ORC_PAGE_SIZE   = 25;

const CTRL = 'bg-bg border border-card_border rounded-lg px-2.5 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent';

function Pager({ page, totalPages, count, onGo }) {
  if (totalPages <= 1) return null;
  const btn = 'px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main';
  return (
    <div className="flex gap-1.5 justify-center items-center mt-3 text-[10px] text-subtext">
      <button className={btn} disabled={page === 0} onClick={() => onGo(0)}>«</button>
      <button className={btn} disabled={page === 0} onClick={() => onGo(page - 1)}>‹</button>
      <span className="px-2">{page + 1} / {totalPages} <span className="opacity-60 ml-1">({count} registros)</span></span>
      <button className={btn} disabled={page >= totalPages - 1} onClick={() => onGo(page + 1)}>›</button>
      <button className={btn} disabled={page >= totalPages - 1} onClick={() => onGo(totalPages - 1)}>»</button>
    </div>
  );
}

// ── Componente principal ───────────────────────────────────────────
export default function CRM({ refreshTrigger }) {
  // selectedVendedor deve ser declarado ANTES de useFilteredDados (é passado como parâmetro)
  const [selectedVendedor, setSelectedVendedor] = useState('');

  const { data, loading, error, isEmpty } = useFilteredDados(
    'crm',
    selectedVendedor ? { vendedor: selectedVendedor } : {},
    refreshTrigger
  );
  const { metas } = useMetas();
  const mIndividuais = metas?.metas_individuais ?? {};

  const vendedores = useMemo(() => (
    [...new Set((data?.ranking_vendedores ?? []).map(r => r.Vendedor).filter(Boolean))].sort()
  ), [data]);

  // ── Inativos — filtros e paginação ───────────────────────────
  const [inatFiltroAno, setInatFiltroAno] = useState('');
  const [inatFiltroCod, setInatFiltroCod] = useState('');
  const [inatPage,      setInatPage]      = useState(0);

  const anosInat = useMemo(() => {
    const sel = selectedVendedor.trim().toLowerCase();
    const anos = new Set(
      (data?.inativos_lista ?? [])
        .filter(r => !sel || (r.ultimo_vendedor ?? '').trim().toLowerCase() === sel)
        .map(r => { const m = String(r.ultima_compra ?? '').match(/^(\d{4})/); return m ? m[1] : null; })
        .filter(Boolean)
    );
    return [...anos].sort().reverse();
  }, [data, selectedVendedor]);

  const inatFiltrados = useMemo(() => {
    const sel = selectedVendedor.trim().toLowerCase();
    const cod = inatFiltroCod.trim().toLowerCase();
    return (data?.inativos_lista ?? []).filter(r => {
      if (sel && (r.ultimo_vendedor ?? '').trim().toLowerCase() !== sel) return false;
      if (inatFiltroAno) {
        const m = String(r.ultima_compra ?? '').match(/^(\d{4})/);
        if (!m || m[1] !== inatFiltroAno) return false;
      }
      if (cod && !String(r.CodCli ?? '').toLowerCase().includes(cod)) return false;
      return true;
    });
  }, [data, inatFiltroAno, inatFiltroCod, selectedVendedor]);

  const inatTotalPages = Math.max(1, Math.ceil(inatFiltrados.length / INAT_PAGE_SIZE));
  const inatPageRows   = inatFiltrados.slice(inatPage * INAT_PAGE_SIZE, (inatPage + 1) * INAT_PAGE_SIZE);

  function setFiltroAno(v) { setInatFiltroAno(v); setInatPage(0); }
  function setFiltroCod(v) { setInatFiltroCod(v); setInatPage(0); }

  // ── Clientes em Risco — filtro é MÁXIMO ("até X dias") ───────
  const [riscoFiltroMax, setRiscoFiltroMax] = useState('');
  const [riscoFiltroCod, setRiscoFiltroCod] = useState('');
  const [riscoPage,      setRiscoPage]      = useState(0);

  const riscoFiltrados = useMemo(() => {
    const sel = selectedVendedor.trim().toLowerCase();
    const cod = riscoFiltroCod.trim().toLowerCase();
    const max = riscoFiltroMax ? parseInt(riscoFiltroMax, 10) : 0;
    return (data?.clientes_risco ?? []).filter(r => {
      if (sel && (r.ultimo_vendedor ?? '').trim().toLowerCase() !== sel) return false;
      if (max > 0 && (r.dias_inativo ?? 0) > max) return false;
      if (cod && !String(r.CodCli ?? '').toLowerCase().includes(cod)) return false;
      return true;
    });
  }, [data, riscoFiltroMax, riscoFiltroCod, selectedVendedor]);

  const riscoTotalPages = Math.max(1, Math.ceil(riscoFiltrados.length / RISCO_PAGE_SIZE));
  const riscoPageRows   = riscoFiltrados.slice(riscoPage * RISCO_PAGE_SIZE, (riscoPage + 1) * RISCO_PAGE_SIZE);

  function setRiscoMax(v) { setRiscoFiltroMax(v); setRiscoPage(0); }
  function setRiscoCod(v) { setRiscoFiltroCod(v); setRiscoPage(0); }

  // ── Orçamentos Abertos — busca + paginação (client-side) ─────
  const [orcBusca, setOrcBusca] = useState('');
  const [orcPage,  setOrcPage]  = useState(0);

  const orcFiltrados = useMemo(() => {
    const sel = selectedVendedor.trim().toLowerCase();
    const q = orcBusca.trim().toLowerCase();
    return (data?.orc_abertos_lista ?? []).filter(r => {
      if (sel && (r.vendedor ?? '').trim().toLowerCase() !== sel) return false;
      if (q && !(String(r.cliente ?? '').toLowerCase().includes(q) ||
                 String(r.NrOrcPedVnd ?? '').toLowerCase().includes(q))) return false;
      return true;
    });
  }, [data, orcBusca, selectedVendedor]);

  const orcTotalPages = Math.max(1, Math.ceil(orcFiltrados.length / ORC_PAGE_SIZE));
  const orcPageRows   = orcFiltrados.slice(orcPage * ORC_PAGE_SIZE, (orcPage + 1) * ORC_PAGE_SIZE);

  useEffect(() => { setInatPage(0); setRiscoPage(0); setOrcPage(0); }, [selectedVendedor]);

  const rankingComMeta = useMemo(() => {
    const sel = selectedVendedor.trim().toLowerCase();
    const rows = (data?.ranking_vendedores ?? []).map(r => {
      const meta = Object.entries(mIndividuais).find(
        ([k]) => k.trim().toLowerCase() === (r.Vendedor ?? '').trim().toLowerCase()
      )?.[1];
      return { ...r, _pct_meta: meta > 0 ? Math.round((r.valor_convertido ?? 0) / meta * 100) : null };
    });
    return sel ? rows.filter(r => (r.Vendedor ?? '').trim().toLowerCase() === sel) : rows;
  }, [data, mIndividuais, selectedVendedor]);

  // Referência estável — NUNCA `data?.x ?? []` direto (novo [] a cada render)
  const canceladosVend = useMemo(() => {
    const all = data?.cancelados_por_vendedor ?? [];
    if (!selectedVendedor) return all;
    const sel = selectedVendedor.trim().toLowerCase();
    return all.filter(r => (r.Vendedor ?? '').trim().toLowerCase() === sel);
  }, [data, selectedVendedor]);

  const rankingComCanc = useMemo(() => {
    const cancMap = Object.fromEntries(canceladosVend.map(r => [r.Vendedor, r.cancelados]));
    return rankingComMeta.map(r => ({ ...r, cancelados: cancMap[r.Vendedor] ?? 0 }));
  }, [rankingComMeta, canceladosVend]);

  // KPI "Em Risco" espelha o limiar do bot (>=60d); a tabela cobre 40–89d
  const qtdRiscoVend = useMemo(() => {
    if (!selectedVendedor) return null;
    const sel = selectedVendedor.trim().toLowerCase();
    return (data?.clientes_risco ?? []).filter(
      r => (r.ultimo_vendedor ?? '').trim().toLowerCase() === sel && (r.dias_inativo ?? 0) >= 60
    ).length;
  }, [data, selectedVendedor]);

  const qtdInatVend = useMemo(() => {
    if (!selectedVendedor) return null;
    const sel = selectedVendedor.trim().toLowerCase();
    return (data?.inativos_lista ?? []).filter(
      r => (r.ultimo_vendedor ?? '').trim().toLowerCase() === sel
    ).length;
  }, [data, selectedVendedor]);

  // ── Guards ────────────────────────────────────────────────────
  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">Carregando dados de CRM…</div>
  );
  if (error && !data) return (
    <div className="flex items-center justify-center h-64 text-accent_red text-sm">Erro ao carregar dados: {error}</div>
  );
  if (isEmpty) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      <div className="text-center space-y-1">
        <p>Bot CRM está processando dados…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  );

  // ── KPIs ──────────────────────────────────────────────────────
  const taxaConv  = data?.taxa_conversao_pct ?? 0;
  const deltaTaxa = data?.delta_taxa_conv    ?? null;
  const pipeline  = data?.valor_orcado       ?? 0;
  const deltaPipe = data?.delta_valor_orcado ?? null;
  const fatLiq    = data?.fat_liq_mes        ?? null;
  const deltaFat  = fatLiq != null && data?.fat_liq_ant != null ? fatLiq - data.fat_liq_ant : null;
  const qtdInat   = qtdInatVend  ?? (data?.qtd_inativos ?? 0);
  const qtdRisco  = qtdRiscoVend ?? (data?.qtd_em_risco ?? 0);
  const riscoTotal = selectedVendedor
    ? (data?.clientes_risco ?? []).filter(r => (r.ultimo_vendedor ?? '').trim().toLowerCase() === selectedVendedor.trim().toLowerCase()).length
    : (data?.clientes_risco?.length ?? 0);
  const inatTotal = qtdInatVend ?? (data?.inativos_lista?.length ?? 0);
  const taxaColor = taxaConv >= 40 ? '#4ade80' : taxaConv >= 25 ? '#fbbf24' : '#f87171';
  const globalHint = selectedVendedor ? ' (global)' : '';

  const deltaSub = (delta, unit) =>
    delta == null || delta === 0 ? undefined
      : `${delta > 0 ? '↑ +' : '↓ '}${Math.abs(delta)}${unit} vs mês anterior`;

  return (
    <div className="p-4">

      {/* ── Cabeçalho ── */}
      <div className="flex items-end justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-text_main text-lg font-bold leading-tight">CRM</h1>
          <p className="text-subtext text-[11px]">
            Gestão comercial e carteira de clientes
            {data?.ultimo_update && <> · Atualizado {data.ultimo_update}</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={selectedVendedor} onChange={e => setSelectedVendedor(e.target.value)}
            className={CTRL} style={{ minWidth: 200, borderColor: selectedVendedor ? AZUL : undefined, color: selectedVendedor ? '#79c0ff' : undefined }}>
            <option value="">Todos os vendedores</option>
            {vendedores.map(v => <option key={v} value={v}>{v}</option>)}
          </select>
          {selectedVendedor && (
            <button onClick={() => setSelectedVendedor('')}
              className="text-[11px] px-2.5 py-1.5 rounded-lg border border-card_border text-subtext hover:text-text_main">
              × Limpar
            </button>
          )}
        </div>
      </div>

      {/* ── Visão Geral ── */}
      <SectionLabel first>Visão Geral do Mês</SectionLabel>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-8 gap-2.5">
        <KpiCard label="Taxa de Conversão" value={pct(taxaConv)} valueColor={taxaColor}
          sub={deltaSub(deltaTaxa, 'pp') ?? 'faturamento líquido ÷ valor em negociação'} topBorder={AZUL} />
        <KpiCard label="Pipeline do Mês (R$)" value={brl(pipeline)}
          sub={deltaSub(deltaPipe != null ? Math.round(deltaPipe / 1000) : null, 'k') ?? 'orçamentos em aberto no mês'} topBorder={VERDE} />
        <KpiCard label="Faturado no Mês (R$)" value={fatLiq != null ? brl(fatLiq) : '—'} valueColor="#4ade80"
          sub={deltaSub(deltaFat != null ? Math.round(deltaFat / 1000) : null, 'k') ?? 'faturamento líquido · base do Dashboard'} topBorder={VERDE} />
        <KpiCard label="Propostas já no Caixa (R$)" value={data?.valor_faturadas != null ? brl(data.valor_faturadas) : '—'} valueColor="#79c0ff"
          sub="propostas do mês que já viraram NF" topBorder={AZUL} />
        <KpiCard label="Clientes Ativos" value={fmtInt(data?.qtd_ativos_mes_real)}
          sub={`compraram no mês${globalHint}`} topBorder={AZUL} />
        <KpiCard label="Clientes Novos" value={fmtInt(data?.clientes_novos_qtd)}
          sub={`1ª compra · ${fmtInt(data?.novos_cadastros_mes)} cadastros${globalHint}`}
          variant="success" topBorder={VERDE} />
        <KpiCard label="Em Risco" value={String(qtdRisco)}
          sub="60–89 dias sem compra" variant="warning" topBorder={AMBAR} />
        <KpiCard label="Clientes Inativos" value={String(qtdInat)}
          sub="sem compra > 90 dias" variant="error" topBorder={VERM} />
      </div>

      {/* ── Funil + Evolução ── */}
      <SectionLabel>Funil e Evolução</SectionLabel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        <Card>
          <CardTitle right={selectedVendedor ? 'vendedor selecionado' : 'mês atual'}>Funil do Mês</CardTitle>
          <FunnelBars etapas={data?.funil_etapas ?? []} />
          <p className="text-subtext text-[10px] mt-2 opacity-70">
            Pense numa loja: <b>Em Negociação</b> = todos que entraram na loja no mês · <b>Fechadas</b> = disseram “pode fechar” (viraram pedido) · <b>Faturadas</b> = já passaram no caixa, nota emitida. O card “Faturado no Mês” é o caixa inteiro — inclui vendas sem orçamento e propostas de meses anteriores. (Técnico: TbOrcPedVnd por emissão, universo 1+2, NF com Fat=1.)
          </p>
        </Card>
        <Card>
          <CardTitle right={selectedVendedor ? 'dados globais' : 'últimas 4 semanas'}>Evolução Semanal</CardTitle>
          <AreaChart
            data={data?.evolucao_semanal ?? []}
            xKey="inicio_semana"
            areas={[
              { key: 'propostas',   label: 'Propostas'   },
              { key: 'convertidos', label: 'Convertidos' },
            ]}
            xFormatter={s => { const m = String(s ?? '').match(/\d{4}-(\d{2})-(\d{2})/); return m ? `${m[2]}/${m[1]}` : (s ?? ''); }}
            colors={[AZUL, VERDE]}
            height={190}
          />
        </Card>
      </div>

      {/* ── Equipe de Vendas ── */}
      <SectionLabel>Equipe de Vendas</SectionLabel>
      <Card>
        <CardTitle right="mês atual">Ranking de Vendedores</CardTitle>
        <DataTable columns={RANKING_COLS} rows={rankingComCanc} />
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-2.5 mt-2.5">
        <Card>
          <CardTitle>Ticket Médio por Vendedor</CardTitle>
          <BarChart
            data={rankingComCanc.slice(0, 8)}
            xKey="Vendedor"
            bars={[{ key: 'ticket_medio', label: 'Ticket Médio', formatter: shortBrl }]}
            tooltipExtra={[{ key: 'convertidos', label: 'Vendas' }]}
            xFormatter={name => (name ?? '').split(' ')[0]}
            colors={[AZUL]}
            height={200}
          />
        </Card>
        <Card>
          <CardTitle right="traço = 80%">% de Meta por Vendedor</CardTitle>
          <BulletBars rows={rankingComMeta.slice(0, 8)} metas={mIndividuais} />
        </Card>
        <Card>
          <CardTitle>Convertidos vs Cancelados</CardTitle>
          <BarChart
            data={rankingComCanc.slice(0, 8)}
            xKey="Vendedor"
            bars={[
              { key: 'convertidos', label: 'Convertidos' },
              { key: 'cancelados',  label: 'Cancelados'  },
            ]}
            xFormatter={name => (name ?? '').split(' ')[0]}
            colors={[VERDE, VERM]}
            height={200}
          />
        </Card>
      </div>

      {/* ── Oportunidades — Orçamentos Abertos ── */}
      <SectionLabel>Oportunidades — Orçamentos Abertos (90 dias)</SectionLabel>
      <Card>
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-text_main text-sm font-semibold">
            {fmtInt(data?.orc_abertos_qtd)} orçamentos
            <span className="text-subtext font-normal"> · {brl(data?.orc_abertos_valor)} em aberto{globalHint}</span>
          </span>
          <div className="flex-1" />
          <input type="text" placeholder="Buscar cliente ou nº…" value={orcBusca}
            onChange={e => { setOrcBusca(e.target.value); setOrcPage(0); }}
            className={`${CTRL} w-52`} />
        </div>
        {orcPageRows.length === 0 ? (
          <div className="text-center py-8 text-subtext text-xs">Nenhum orçamento encontrado.</div>
        ) : (
          <DataTable columns={ORC_COLS} rows={orcPageRows} />
        )}
        <Pager page={orcPage} totalPages={orcTotalPages} count={orcFiltrados.length} onGo={setOrcPage} />
        <p className="text-subtext text-[10px] mt-2 opacity-70">
          Top 100 orçamentos não convertidos por valor (follow-up comercial) · badge: verde ≤7d · âmbar ≤30d · vermelho +30d.
        </p>
      </Card>

      {/* ── Carteira de Clientes ── */}
      <SectionLabel>Carteira de Clientes</SectionLabel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        <Card>
          <CardTitle right="mês atual">Top Clientes do Mês</CardTitle>
          <DataTable columns={TOP_COLS} rows={data?.top_clientes ?? []} />
        </Card>
        <Card>
          <CardTitle right={`1ª compra no mês${globalHint}`}>Clientes Novos</CardTitle>
          {(data?.clientes_novos_lista ?? []).length === 0 ? (
            <div className="text-center py-8 text-subtext text-xs">Nenhum cliente novo neste mês.</div>
          ) : (
            <DataTable columns={NOVOS_COLS} rows={(data?.clientes_novos_lista ?? []).slice(0, 10)} />
          )}
        </Card>
        <Card>
          <CardTitle right={selectedVendedor ? 'dados globais' : 'dias sem compra'}>Faixas de Inatividade</CardTitle>
          <ResponsiveContainer width="100%" height={200}>
            <RC data={data?.faixas_inatividade ?? []} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="faixa" tick={{ fill: '#8b949e', fontSize: 10 }} />
              <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} allowDecimals={false} />
              <RCTooltip
                contentStyle={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }}
                labelStyle={{ color: '#e6edf3' }} itemStyle={{ color: '#8b949e' }} />
              <Bar dataKey="qtd" name="Clientes" radius={[3, 3, 0, 0]}>
                {(data?.faixas_inatividade ?? []).map((_, i) => (
                  <Cell key={i} fill={HIST_COLORS[i] ?? VERM} />
                ))}
                <LabelList dataKey="qtd" position="top" style={{ fill: '#e6edf3', fontSize: 11, fontWeight: 700 }} />
              </Bar>
            </RC>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ── Clientes em Risco ── */}
      <SectionLabel>Atenção — Clientes em Risco</SectionLabel>
      <Card>
        <CardTitle right={`${riscoFiltrados.length} de ${riscoTotal} clientes · zona 40–89 dias`}>Clientes em Risco</CardTitle>
        <div className="flex gap-2 mb-3 flex-wrap">
          <select value={riscoFiltroMax} onChange={e => setRiscoMax(e.target.value)} className={CTRL}>
            <option value="">Todos os dias</option>
            {[40, 50, 60, 70, 80, 90].map(d => <option key={d} value={d}>Até {d} dias</option>)}
          </select>
          <input type="text" placeholder="Filtrar por código…" value={riscoFiltroCod}
            onChange={e => setRiscoCod(e.target.value)} className={`${CTRL} w-40`} />
          {(riscoFiltroMax || riscoFiltroCod) && (
            <button onClick={() => { setRiscoMax(''); setRiscoCod(''); }}
              className="text-[11px] px-2.5 rounded-lg border border-card_border text-subtext hover:text-text_main">
              Limpar filtros
            </button>
          )}
        </div>
        {riscoPageRows.length === 0 ? (
          <div className="text-center py-8 text-subtext text-xs">Nenhum cliente encontrado com estes filtros.</div>
        ) : (
          <DataTable columns={RISCO_COLS} rows={riscoPageRows} />
        )}
        <Pager page={riscoPage} totalPages={riscoTotalPages} count={riscoFiltrados.length} onGo={setRiscoPage} />
      </Card>

      {/* ── Clientes Inativos ── */}
      <SectionLabel>Atenção — Clientes Inativos</SectionLabel>
      <Card>
        <CardTitle right={`${inatFiltrados.length} de ${inatTotal} clientes · último vendedor`}>Clientes Inativos</CardTitle>
        <div className="flex gap-2 mb-3 flex-wrap">
          <select value={inatFiltroAno} onChange={e => setFiltroAno(e.target.value)} className={CTRL}>
            <option value="">Todos os anos</option>
            {anosInat.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <input type="text" placeholder="Filtrar por código…" value={inatFiltroCod}
            onChange={e => setFiltroCod(e.target.value)} className={`${CTRL} w-40`} />
          {(inatFiltroAno || inatFiltroCod) && (
            <button onClick={() => { setFiltroAno(''); setFiltroCod(''); }}
              className="text-[11px] px-2.5 rounded-lg border border-card_border text-subtext hover:text-text_main">
              Limpar filtros
            </button>
          )}
        </div>
        <DataTable columns={INAT_COLS} rows={inatPageRows} />
        <Pager page={inatPage} totalPages={inatTotalPages} count={inatFiltrados.length} onGo={setInatPage} />
      </Card>

    </div>
  );
}
