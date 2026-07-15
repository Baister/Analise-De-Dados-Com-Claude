import { useState, useMemo } from 'react';
import { useDados } from '../hooks/useApi';
import KpiCard from '../components/KpiCard';
import DataTable from '../components/DataTable';
import LineChart from '../charts/LineChart';
import BarChart from '../charts/BarChart';
import PieChart from '../charts/PieChart';
import { brl, shortBrl, fmtDate } from '../utils/format';

const PAGE_SIZE = 50;

const fmtInt = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }));
const fmtQtd = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 }));
// Venda líquida = vendas − devoluções; negativo significa mais devolução que venda
const fmtLiq = v => {
  if (v == null) return '—';
  const n = Number(v);
  return n < 0 ? `${fmtInt(n)} (devolveu mais que vendeu)` : fmtInt(n);
};

// Cores semânticas fixas (paleta da casa)
const ABC_COLOR = { A: '#238636', B: '#d29922', C: '#da3633' };

function SectionLabel({ children, first }) {
  return (
    <p
      className="text-[10px] text-subtext uppercase mb-[7px]"
      style={{ letterSpacing: '1px', marginTop: first ? 0 : 18 }}
    >
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
      <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>
        {children}
      </p>
      {right && <span className="text-[9px] text-subtext opacity-70">{right}</span>}
    </div>
  );
}

function AbcBadge({ classe }) {
  const c = ABC_COLOR[classe] || '#8b949e';
  return (
    <span
      className="inline-block font-bold rounded"
      style={{ fontSize: 9, padding: '1px 7px', background: `${c}26`, color: c }}
    >
      {classe ?? '—'}
    </span>
  );
}

function fmtTempo(dias) {
  if (dias == null) return 'Nunca vendido';
  if (dias >= 365) {
    const a = Math.floor(dias / 365);
    const m = Math.floor((dias % 365) / 30);
    return m > 0 ? `${a}a ${m}m` : `${a} ano${a !== 1 ? 's' : ''}`;
  }
  if (dias >= 30) return `${Math.floor(dias / 30)} meses`;
  return `${dias} dias`;
}

// ─── Situações da tabela detalhada (cada uma com sua fonte e colunas) ───────
const SITUACOES = [
  { key: 'todos',  label: 'Todos os itens',    color: '#1f6feb' },
  { key: 'min',    label: 'Abaixo do Mínimo',  color: '#d29922' },
  { key: 'parado', label: 'Parado 90+ dias',   color: '#a371f7' },
  { key: 'zerado', label: 'Sem Estoque',       color: '#da3633' },
];

const COLS_TODOS = [
  { key: 'CodItem',        label: 'Cód.' },
  { key: 'DescrItem',      label: 'Descrição' },
  { key: 'DescrMarca',     label: 'Marca' },
  { key: 'QtdEstq',        label: 'Estq',      align: 'right', render: fmtQtd },
  { key: 'QtdEstqDisp',    label: 'Disp',      align: 'right', render: fmtQtd },
  { key: 'EstqMin',        label: 'Mín',       align: 'right', render: v => (v > 0 ? fmtQtd(v) : '—') },
  { key: 'giro90d',        label: 'Giro 90d',  align: 'right', render: v => (v ?? 0).toFixed(2) },
  { key: 'cobertura_dias', label: 'Cobert.',   align: 'right', render: v => (v == null ? '—' : `${v}d`) },
  { key: 'abc',            label: 'ABC',       render: v => <AbcBadge classe={v} /> },
  { key: 'VlrEstq',        label: 'Valor',     align: 'right', render: brl },
];

const COLS_MIN = [
  { key: 'CodItem',     label: 'Cód.' },
  { key: 'DescrItem',   label: 'Descrição' },
  { key: 'DescrMarca',  label: 'Marca' },
  { key: 'QtdEstqDisp', label: 'Disponível', align: 'right', render: fmtQtd },
  { key: 'EstqMin',     label: 'Mínimo',     align: 'right', render: fmtQtd },
  { key: 'falta',       label: 'Falta',      align: 'right',
    render: v => <span style={{ color: '#d29922', fontWeight: 700 }}>{fmtQtd(v)}</span> },
];

const COLS_PARADO = [
  { key: 'CodItem',        label: 'Cód.' },
  { key: 'DescrItem',      label: 'Descrição' },
  { key: 'DescrMarca',     label: 'Marca' },
  { key: 'QtdEstq',        label: 'Qtd',          align: 'right', render: fmtQtd },
  { key: 'VlrEstq',        label: 'Vlr Imobilizado', align: 'right', render: brl },
  { key: 'DiasSemVndReal', label: 'Tempo parado', render: v => fmtTempo(v) },
  { key: 'DtUltVnd',       label: 'Última venda', render: v => (v ? fmtDate(v) : '—') },
];

const COLS_ZERADO = [
  { key: 'CodItem',    label: 'Cód.' },
  { key: 'DescrItem',  label: 'Descrição' },
  { key: 'DescrMarca', label: 'Marca' },
  { key: 'VlrEstq',    label: 'Vlr Estq',     align: 'right', render: brl },
  { key: 'DtUltVnd',   label: 'Última venda', render: v => (v ? fmtDate(v) : '—') },
];

const COLS_MAP = { todos: COLS_TODOS, min: COLS_MIN, parado: COLS_PARADO, zerado: COLS_ZERADO };

const truncate = (s, n = 14) => {
  const t = String(s ?? '');
  return t.length > n ? t.slice(0, n - 1) + '…' : t;
};

// ─── Componente ─────────────────────────────────────────────────────────────
export default function Estoque({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useDados('estoque', refreshTrigger);

  const [situacao, setSituacao]     = useState('todos');
  const [textoBusca, setTextoBusca] = useState('');
  const [marcaSel, setMarcaSel]     = useState('todas');
  const [abcSel, setAbcSel]         = useState('todas');
  const [page, setPage]             = useState(0);

  const tabela       = data?.tabela_detalhada ?? [];
  const abcResumo    = data?.abc_resumo ?? [];
  const porMarca     = data?.por_marca ?? [];
  const entradasSaidas = data?.entradas_saidas ?? [];
  const evolucao     = data?.evolucao_estimada ?? [];
  const evolucaoReal = data?.evolucao_real ?? [];
  const giroTop      = data?.giro_top ?? [];
  const giroBottom   = data?.giro_bottom ?? [];

  const marcasOpts = useMemo(
    () => ['todas', ...porMarca.map(m => m.DescrMarca).filter(Boolean)],
    [porMarca]
  );

  // Fonte de linhas conforme a situação selecionada
  const fonteRows = useMemo(() => {
    if (situacao === 'min')    return data?.abaixo_min_lista ?? [];
    if (situacao === 'parado') return data?.parado_lista ?? [];
    if (situacao === 'zerado') return data?.zerados_lista ?? [];
    return tabela;
  }, [situacao, data, tabela]);

  // Filtros client-side: texto + marca (todas as situações) + classe ABC (só "todos")
  const rowsFiltradas = useMemo(() => {
    const q = textoBusca.trim().toLowerCase();
    return fonteRows.filter(r => {
      if (q && !(String(r.DescrItem ?? '').toLowerCase().includes(q) ||
                 String(r.CodItem ?? '').toLowerCase().includes(q))) return false;
      if (marcaSel !== 'todas' && r.DescrMarca !== marcaSel) return false;
      if (situacao === 'todos' && abcSel !== 'todas' && r.abc !== abcSel) return false;
      return true;
    });
  }, [fonteRows, textoBusca, marcaSel, abcSel, situacao]);

  const totalPages = Math.max(Math.ceil(rowsFiltradas.length / PAGE_SIZE), 1);
  const rowsPage = useMemo(
    () => rowsFiltradas.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE),
    [rowsFiltradas, page]
  );

  // Dados dos gráficos
  const abcPie = useMemo(
    () => abcResumo.map(a => ({ ...a, label: `Classe ${a.classe}` })),
    [abcResumo]
  );
  const marcaChart = useMemo(() => porMarca.slice(0, 10), [porMarca]);
  // Nome curto no eixo Y (nome completo fica no tooltip via DescrItem)
  const giroTopChart = useMemo(
    () => giroTop.map(r => ({ ...r, DescrCurta: truncate(r.DescrItem, 18) })),
    [giroTop]
  );
  const giroBottomChart = useMemo(
    () => giroBottom.map(r => ({ ...r, DescrCurta: truncate(r.DescrItem, 18) })),
    [giroBottom]
  );

  function selectSituacao(key) {
    setSituacao(key);
    setPage(0);
    setTextoBusca('');
    if (key !== 'todos') setAbcSel('todas');
  }

  // ── Early returns ──
  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      Carregando dados de estoque…
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
        <p>Bot Estoque está processando dados…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  );

  const situacaoAtiva = SITUACOES.find(s => s.key === situacao) ?? SITUACOES[0];

  return (
    <div className="p-4">

      {/* ── Cabeçalho ── */}
      <div className="flex items-end justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-text_main text-lg font-bold leading-tight">Estoque</h1>
          <p className="text-subtext text-[11px]">
            Visão geral, Curva ABC, giro e cobertura · {fmtInt(data?.skus)} SKUs
            {data?.ultimo_update && <> · Atualizado {data.ultimo_update}</>}
          </p>
        </div>
      </div>

      {/* ── KPIs ── */}
      <SectionLabel first>Visão Geral</SectionLabel>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2.5">
        <KpiCard label="Valor em Estoque" value={brl(data?.valor_total_estoque)}
          sub="custo dos itens" topBorder="#1f6feb" gradient="rgba(31,111,235,0.10)" />
        <KpiCard label="Qtd em Estoque" value={fmtInt(data?.qtd_total)}
          sub="unidades armazenadas" topBorder="#8b949e" />
        <KpiCard label="SKUs" value={fmtInt(data?.skus)}
          sub={`${fmtInt(data?.skus_com_estoque)} com estoque`} topBorder="#1f6feb" />
        <KpiCard label="Abaixo do Mínimo" value={String(data?.abaixo_min_qtd ?? 0)}
          sub={`de ${data?.abaixo_min_total_config ?? 0} com mín. configurado`}
          variant="warning" topBorder="#d29922" />
        <KpiCard label="Sem Estoque" value={String(data?.itens_zerados ?? 0)}
          sub="disponível ≤ 0" variant="error" topBorder="#da3633" />
        <KpiCard label="Estoque Parado" value={String(data?.parado_qtd ?? 0)}
          sub={`${brl(data?.parado_valor)} imobilizado`}
          valueColor="#a371f7" topBorder="#a371f7" />
        <KpiCard label="Cobertura Média" value={data?.cobertura_media_dias != null ? `${data.cobertura_media_dias} dias` : '—'}
          sub="disponível ÷ demanda 90d" variant="success" topBorder="#238636" />
      </div>

      {/* ── Curva ABC ── */}
      <SectionLabel>Curva ABC — por valor vendido (90 dias)</SectionLabel>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: '1fr 1fr 1.4fr' }}>
        <div className="flex flex-col gap-2.5">
          {abcResumo.map(a => (
            <div key={a.classe}
              className="bg-card border border-card_border rounded-lg px-4 py-2.5 flex items-center gap-3"
              style={{ borderLeft: `3px solid ${ABC_COLOR[a.classe]}` }}>
              <span className="text-xl font-bold" style={{ color: ABC_COLOR[a.classe] }}>{a.classe}</span>
              <div className="flex-1">
                <p className="text-text_main text-sm font-semibold leading-tight">
                  {fmtInt(a.itens)} itens
                  <span className="text-subtext font-normal"> · {a.pct_valor_vendido}% das vendas</span>
                </p>
                <p className="text-subtext text-[10px]">{brl(a.valor_estoque)} em estoque</p>
              </div>
            </div>
          ))}
        </div>
        <Card>
          <CardTitle>Valor em Estoque por Classe</CardTitle>
          <PieChart
            data={abcPie} nameKey="label" valueKey="valor_estoque" showValue
            colors={[ABC_COLOR.A, ABC_COLOR.B, ABC_COLOR.C]}
            tooltipContext={{
              title: 'Valor em estoque',
              formula: 'Classe pela participação no valor vendido 90d: A=80% · B=15% · C=5%',
              extra: [
                { key: 'itens', label: 'Itens', formatter: fmtInt },
                { key: 'val_vendido_90d', label: 'Vendido 90d', formatter: brl },
              ],
            }}
          />
        </Card>
        <Card>
          <CardTitle right="top 10 · valor de estoque">Valor por Marca</CardTitle>
          <BarChart
            data={marcaChart} xKey="DescrMarca" horizontal height={230} yAxisWidth={96}
            bars={[{ key: 'valor_estoque', label: 'Valor em estoque', formatter: shortBrl }]}
            colors={['#1f6feb']}
            tooltipExtra={[
              { key: 'qtd_itens', label: 'Itens', formatter: fmtInt },
              { key: 'quantidade_total', label: 'Unidades', formatter: fmtInt },
            ]}
          />
        </Card>
      </div>

      {/* ── Evolução ── */}
      <SectionLabel>Evolução do Estoque (12 meses)</SectionLabel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        <Card>
          <CardTitle right="reconstruído pelos movimentos · custo médio atual">
            Valor em Estoque (R$) — estimado
          </CardTitle>
          <LineChart data={evolucao} xKey="mes"
            lines={[{ key: 'valor_estimado', label: 'Valor estimado', formatter: shortBrl }]}
            colors={['#1f6feb']} />
        </Card>
        <Card>
          <CardTitle right="reconstruído pelos movimentos">
            Quantidade em Estoque (unidades)
          </CardTitle>
          <LineChart data={evolucao} xKey="mes"
            lines={[{ key: 'qtd', label: 'Quantidade', formatter: fmtInt }]}
            colors={['#238636']} />
        </Card>
      </div>
      <p className="text-subtext text-[10px] mt-1.5 opacity-70">
        Série reconstruída a partir das entradas/saídas (o ERP não guarda foto diária do estoque).
        Snapshots reais passaram a ser gravados diariamente
        {evolucaoReal.length > 0 && <> desde {fmtDate(evolucaoReal[0].day)}</>} — com o tempo, a
        evolução se torna 100% medida.
      </p>

      {/* ── Entradas × Saídas ── */}
      <SectionLabel>Entradas × Saídas por Mês</SectionLabel>
      <Card>
        <BarChart
          data={entradasSaidas} xKey="mes" height={240}
          bars={[
            { key: 'entradas', label: 'Entradas', formatter: fmtInt },
            { key: 'saidas',   label: 'Saídas',   formatter: fmtInt },
          ]}
          colors={['#1f6feb', '#d29922']}
        />
      </Card>

      {/* ── Giro ── */}
      <SectionLabel>Giro de Estoque (90 dias)</SectionLabel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        <Card>
          <CardTitle right="venda líquida 90d ÷ estoque atual">🔥 Maior Rotatividade — top 10</CardTitle>
          <BarChart
            data={giroTopChart} xKey="DescrCurta" horizontal height={260} yAxisWidth={120}
            bars={[{ key: 'giro90d', label: 'Giro 90d', formatter: v => Number(v).toFixed(1) }]}
            colors={['#238636']} showLabels
            tooltipExtra={[
              { key: 'DescrItem',             label: 'Item' },
              { key: 'qtd_vendas_brutas_90d', label: 'Vendas 90d',        formatter: fmtInt },
              { key: 'qtd_devolvida_90d',     label: 'Devoluções 90d',    formatter: fmtInt },
              { key: 'qtd_vendida_90d',       label: 'Venda líquida 90d', formatter: fmtLiq },
              { key: 'QtdEstq',               label: 'Em estoque',        formatter: fmtInt },
              { key: 'cobertura_dias',        label: 'Cobertura',         formatter: v => (v == null ? '—' : `${v} dias`) },
            ]}
          />
        </Card>
        <Card>
          <CardTitle right="menor giro · maior valor parado">🧊 Menor Rotatividade — top 10</CardTitle>
          <BarChart
            data={giroBottomChart} xKey="DescrCurta" horizontal height={260} yAxisWidth={120}
            bars={[{ key: 'VlrEstq', label: 'Valor parado', formatter: shortBrl }]}
            colors={['#da3633']} showLabels
            tooltipExtra={[
              { key: 'DescrItem',             label: 'Item' },
              { key: 'giro90d',               label: 'Giro 90d',          formatter: v => Number(v ?? 0).toFixed(2) },
              { key: 'qtd_vendas_brutas_90d', label: 'Vendas 90d',        formatter: fmtInt },
              { key: 'qtd_devolvida_90d',     label: 'Devoluções 90d',    formatter: fmtInt },
              { key: 'qtd_vendida_90d',       label: 'Venda líquida 90d', formatter: fmtLiq },
              { key: 'QtdEstq',               label: 'Em estoque',        formatter: fmtInt },
            ]}
          />
        </Card>
      </div>

      {/* ── Tabela detalhada ── */}
      <SectionLabel>Tabela Detalhada</SectionLabel>
      <Card>
        {/* Chips de situação */}
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {SITUACOES.map(s => {
            const active = situacao === s.key;
            const count = s.key === 'todos'  ? tabela.length
                        : s.key === 'min'    ? (data?.abaixo_min_lista ?? []).length
                        : s.key === 'parado' ? (data?.parado_lista ?? []).length
                        : (data?.zerados_lista ?? []).length;
            return (
              <button key={s.key} onClick={() => selectSituacao(s.key)}
                className="rounded-full transition-all"
                style={{
                  fontSize: 11, padding: '4px 12px', fontWeight: active ? 700 : 400,
                  background: active ? s.color : '#21262d',
                  color: active ? '#fff' : '#8b949e',
                  border: `1px solid ${active ? s.color : '#30363d'}`,
                }}>
                {s.label} · {fmtInt(count)}
              </button>
            );
          })}
          <div className="flex-1" />
          <input
            type="text" placeholder="Buscar produto ou código…"
            value={textoBusca}
            onChange={e => { setTextoBusca(e.target.value); setPage(0); }}
            className="w-56 px-3 py-1.5 text-xs bg-bg border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent"
          />
          <select
            value={marcaSel}
            onChange={e => { setMarcaSel(e.target.value); setPage(0); }}
            className="bg-bg border border-card_border rounded-lg px-2 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent"
          >
            {marcasOpts.map(m => (
              <option key={m} value={m}>{m === 'todas' ? 'Todas as marcas' : m}</option>
            ))}
          </select>
          {situacao === 'todos' && (
            <select
              value={abcSel}
              onChange={e => { setAbcSel(e.target.value); setPage(0); }}
              className="bg-bg border border-card_border rounded-lg px-2 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent"
            >
              <option value="todas">ABC: todas</option>
              <option value="A">Classe A</option>
              <option value="B">Classe B</option>
              <option value="C">Classe C</option>
            </select>
          )}
        </div>

        <DataTable columns={COLS_MAP[situacao]} rows={rowsPage} />

        {/* Paginação */}
        <div className="flex items-center justify-between mt-2 text-[10px] text-subtext">
          <span>
            {fmtInt(rowsFiltradas.length)} itens
            {situacao !== 'todos' && <> · <span style={{ color: situacaoAtiva.color }}>{situacaoAtiva.label}</span></>}
            {totalPages > 1 && <> · pág {page + 1}/{totalPages}</>}
          </span>
          {totalPages > 1 && (
            <div className="flex items-center gap-1">
              <button disabled={page === 0} onClick={() => setPage(0)}
                className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">«</button>
              <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
                className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">‹</button>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
                className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">›</button>
              <button disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}
                className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">»</button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
