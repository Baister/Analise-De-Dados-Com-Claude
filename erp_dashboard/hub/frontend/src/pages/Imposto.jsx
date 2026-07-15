import { useMemo, useState } from 'react'
import { useDados } from '../hooks/useApi'
import KpiCard from '../components/KpiCard'
import DataTable from '../components/DataTable'
import LineChart from '../charts/LineChart'
import BarChart from '../charts/BarChart'
import PieChart from '../charts/PieChart'
import { brl, pct, shortBrl, fmtDate } from '../utils/format'
import { countBusinessDaysSP, remainingBusinessDaysSP } from '../utils/businessDays'

const AZUL = '#1f6feb', VERDE = '#238636', AMBAR = '#d29922', VERM = '#da3633', ROXO = '#a371f7';
const CFOP_COLORS = [AZUL, VERDE, AMBAR, ROXO, VERM];

const fmtInt = v => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }));
const fmtQtd = v =>
  v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 });

function SectionLabel({ children, first }) {
  return (
    <p className="text-[10px] text-subtext uppercase mb-[7px]"
      style={{ letterSpacing: '1px', marginTop: first ? 0 : 18 }}>
      {children}
    </p>
  )
}

function Card({ children, className = '' }) {
  return (
    <div className={`bg-card border border-card_border rounded-lg p-4 ${className}`}>
      {children}
    </div>
  )
}

function CardTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>{children}</p>
      {right && <span className="text-[9px] text-subtext opacity-70">{right}</span>}
    </div>
  )
}

function Chip({ text, color, bg }) {
  return (
    <span style={{ fontSize: 9, fontWeight: 600, padding: '2px 7px', borderRadius: 9999, background: bg, color }}>
      {text}
    </span>
  )
}

const UF_STYLE = {
  'Dentro do Estado': { color: '#4ade80', bg: 'rgba(34,197,94,0.15)' },
  'Fora do Estado':   { color: '#60a5fa', bg: 'rgba(59,130,246,0.15)' },
  'Exterior':         { color: '#c084fc', bg: 'rgba(168,85,247,0.15)' },
  'Entrada/Outras':   { color: '#94a3b8', bg: 'rgba(148,163,184,0.15)' },
}

// Subtítulo de delta vs mês anterior (verde=alta, vermelho=queda; neutro p/ alíquota)
const deltaSub = (delta, fmt = brl, sufixo = 'vs mês anterior') => {
  if (delta == null || delta === 0) return undefined;
  const seta = delta > 0 ? '↑ +' : '↓ −';
  return `${seta}${fmt(Math.abs(delta))} ${sufixo}`;
};

const ITENS_PAGE_SIZE = 50;

export default function Imposto({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useDados('imposto', refreshTrigger)

  const [itemBusca, setItemBusca] = useState('');
  const [itemPage,  setItemPage]  = useState(0);

  const kpis      = data?.kpis ?? {}
  const deltas    = data?.deltas ?? {}
  const diario    = data?.icms_diario ?? []
  const evolucao  = data?.evolucao_mensal ?? []
  const porCfop   = data?.por_cfop ?? []
  const resumoUf  = data?.resumo_uf ?? []
  const cfopEvo   = data?.cfop_evolucao ?? []
  const cfopSeries = data?.cfop_series ?? []
  const topNfs    = data?.top_nfs ?? []
  const tribDist  = data?.trib_distribuicao ?? []
  const itens     = data?.itens_tributacao ?? []
  const pisCofins = data?.pis_cofins ?? []
  const mesRef    = data?.mes_referencia ?? ''

  // Projeção do ICMS do mês pelo ritmo de dias úteis (SP) já decorridos
  const projecaoIcms = useMemo(() => {
    const icms = kpis.icms ?? 0;
    if (!icms) return 0;
    const now = new Date();
    const total = countBusinessDaysSP(now.getFullYear(), now.getMonth() + 1);
    const rest  = remainingBusinessDaysSP(now.getFullYear(), now.getMonth() + 1);
    const decorridos = Math.max(total - rest + 1, 1); // hoje conta como decorrido
    return icms / decorridos * total;
  }, [kpis.icms]);

  const cfopChart = useMemo(
    () => [...porCfop].sort((a, b) => (b.icms ?? 0) - (a.icms ?? 0)).slice(0, 10),
    [porCfop]
  )

  const itensFiltrados = useMemo(() => {
    const q = itemBusca.trim().toLowerCase();
    if (!q) return itens;
    return itens.filter(r =>
      String(r.descricao ?? '').toLowerCase().includes(q) ||
      String(r.cod_item ?? '').toLowerCase().includes(q) ||
      String(r.marca ?? '').toLowerCase().includes(q));
  }, [itens, itemBusca]);
  const itemTotalPages = Math.max(1, Math.ceil(itensFiltrados.length / ITENS_PAGE_SIZE));
  const itemPageRows = itensFiltrados.slice(itemPage * ITENS_PAGE_SIZE, (itemPage + 1) * ITENS_PAGE_SIZE);

  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      Carregando dados de impostos…
    </div>
  )
  if (error && !data) return (
    <div className="flex items-center justify-center h-64 text-accent_red text-sm">
      Erro ao carregar dados: {error}
    </div>
  )
  if (isEmpty) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      <div className="text-center space-y-1">
        <p>Bot Imposto está processando dados…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  )

  return (
    <div className="p-4">
      {/* ── Cabeçalho ── */}
      <div className="flex items-end justify-between flex-wrap gap-2 mb-1">
        <div>
          <h1 className="text-text_main text-lg font-bold leading-tight">Imposto</h1>
          <p className="text-subtext text-[11px]">
            ICMS, CFOP e tributação — notas fiscais de venda · mês {mesRef}
            {data?.ultimo_update && <> · Atualizado {data.ultimo_update}</>}
          </p>
        </div>
      </div>

      {/* ── KPIs (com comparativo do mês anterior) ── */}
      <SectionLabel first>Resumo do Mês — comparado ao mês anterior</SectionLabel>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        <KpiCard label="ICMS do Mês (R$)" value={brl(kpis.icms)}
          sub={deltaSub(deltas.icms) ?? 'Débito de ICMS'}
          topBorder={AZUL} gradient="rgba(31,111,235,0.10)" />
        <KpiCard label="Alíquota Efetiva" value={pct(kpis.aliquota_efetiva)}
          sub={deltaSub(deltas.aliquota, v => `${v.toFixed(2)}pp`) ?? 'ICMS ÷ Base'}
          topBorder={VERDE} valueColor="#4ade80" />
        <KpiCard label="Projeção ICMS (mês)" value={brl(projecaoIcms)}
          sub="ritmo atual × dias úteis do mês" topBorder={ROXO} valueColor="#c084fc" />
        <KpiCard label="Faturamento (NFs)" value={brl(kpis.faturamento)}
          sub={deltaSub(deltas.faturamento) ?? 'NFs de venda'} topBorder={AZUL} />
        <KpiCard label="Base de Cálculo (R$)" value={brl(kpis.base_icms)}
          sub="Base ICMS" topBorder="#8b949e" />
        <KpiCard label="Qtde NFs" value={fmtInt(kpis.qtd_nf)}
          sub={`${fmtInt(kpis.nfs_canceladas)} canceladas`}
          variant={kpis.nfs_canceladas > 0 ? 'warning' : 'default'} topBorder={AZUL} />
        <KpiCard label="ICMS-ST (R$)" value={brl(kpis.icms_st)}
          sub="Substituição Tributária" topBorder={ROXO} />
        <KpiCard label="IPI (R$)" value={brl(kpis.ipi)}
          sub="Débito de IPI" topBorder={AMBAR} />
      </div>
      {(kpis.icms_st === 0 && kpis.ipi === 0) && (
        <p className="text-subtext text-[10px] mt-1.5 opacity-70">
          IPI e ICMS-ST aparecem zerados: operação de revenda/comércio (ST retido a montante —
          refletido via CFOP 5405/6404). Os campos ficam prontos caso passem a ter valor.
        </p>
      )}

      {/* ── ICMS diário ── */}
      <SectionLabel>ICMS no Mês — dia a dia</SectionLabel>
      <Card>
        <BarChart
          data={diario} xKey="dia" height={220}
          bars={[{ key: 'icms', label: 'ICMS', formatter: shortBrl }]}
          colors={[AZUL]}
          tooltipExtra={[
            { key: 'faturamento', label: 'Faturamento', formatter: brl },
            { key: 'qtd_nf',      label: 'NFs',         formatter: fmtInt },
          ]}
        />
      </Card>

      {/* ── Evolução 12 meses ── */}
      <SectionLabel>Evolução Mensal (12 meses)</SectionLabel>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: '1.6fr 1fr' }}>
        <Card>
          <CardTitle>ICMS · ICMS-ST · IPI (R$)</CardTitle>
          <LineChart
            data={evolucao} xKey="mes"
            lines={[
              { key: 'icms',    label: 'ICMS',    formatter: shortBrl },
              { key: 'icms_st', label: 'ICMS-ST', formatter: shortBrl },
              { key: 'ipi',     label: 'IPI',     formatter: shortBrl },
            ]}
          />
        </Card>
        <Card>
          <CardTitle>Alíquota Efetiva (%)</CardTitle>
          <LineChart
            data={evolucao} xKey="mes"
            lines={[{ key: 'aliquota', label: 'Alíquota', formatter: v => pct(v) }]}
            colors={[VERDE]}
          />
        </Card>
      </div>

      {/* ── Análise por CFOP ── */}
      <SectionLabel>Análise por CFOP</SectionLabel>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: '1.6fr 1fr' }}>
        <Card>
          <CardTitle>ICMS por CFOP (top 10)</CardTitle>
          <BarChart
            data={cfopChart} xKey="cfop"
            bars={[{ key: 'icms', label: 'ICMS', formatter: shortBrl }]}
            colors={[AZUL]}
            tooltipExtra={[
              { key: 'descricao', label: 'Operação' },
              { key: 'pct_icms',  label: '% do ICMS',   formatter: v => pct(v) },
              { key: 'total',     label: 'Faturamento', formatter: brl },
              { key: 'qtd',       label: 'NFs',         formatter: fmtInt },
            ]}
          />
        </Card>
        <Card>
          <CardTitle>Operações Dentro × Fora do Estado</CardTitle>
          <PieChart
            data={resumoUf} nameKey="label" valueKey="total" showValue formatter={brl}
            tooltipContext={{
              title: 'Faturamento',
              formula: 'Classificação pelo 1º dígito do CFOP: 5=dentro · 6=fora · 7=exterior',
              extra: [{ key: 'icms', label: 'ICMS', formatter: brl }],
            }}
          />
        </Card>
      </div>
      <Card className="mt-2.5">
        <CardTitle right="top 5 CFOPs por ICMS acumulado">Evolução do ICMS por CFOP (6 meses)</CardTitle>
        <LineChart
          data={cfopEvo} xKey="mes"
          lines={cfopSeries.map(c => ({ key: c, label: `CFOP ${c}`, formatter: shortBrl }))}
          colors={CFOP_COLORS}
          height={220}
        />
      </Card>
      <Card className="mt-2.5">
        <CardTitle>Detalhamento por CFOP — {mesRef}</CardTitle>
        <DataTable
          columns={[
            { key: 'cfop', label: 'CFOP' },
            { key: 'descricao', label: 'Operação' },
            { key: 'uf', label: 'Destino', render: v => {
                const s = UF_STYLE[v] || UF_STYLE['Entrada/Outras']
                return <Chip text={v} color={s.color} bg={s.bg} />
            } },
            { key: 'st', label: 'ST', render: v => v
                ? <Chip text="ST" color="#fb923c" bg="rgba(249,115,22,0.15)" />
                : <span className="opacity-30">—</span> },
            { key: 'qtd', label: 'NFs', align: 'right', render: fmtInt },
            { key: 'total', label: 'Faturamento', align: 'right', render: brl },
            { key: 'base_icms', label: 'Base ICMS', align: 'right', render: brl },
            { key: 'icms', label: 'ICMS', align: 'right', render: brl },
            { key: 'pct_icms', label: '% ICMS', align: 'right', render: v => pct(v) },
            { key: 'icms_st', label: 'ICMS-ST', align: 'right', render: brl },
            { key: 'ipi', label: 'IPI', align: 'right', render: brl },
          ]}
          rows={porCfop}
        />
      </Card>

      {/* ── Maiores NFs ── */}
      <SectionLabel>Maiores NFs do Mês por ICMS</SectionLabel>
      <Card>
        <DataTable
          columns={[
            { key: 'nr_nf',   label: 'NF', render: v => <span className="text-subtext" style={{ fontFamily: 'monospace' }}>{v}</span> },
            { key: 'data',    label: 'Emissão', render: v => fmtDate(v) },
            { key: 'cliente', label: 'Cliente' },
            { key: 'cfop',    label: 'CFOP' },
            { key: 'base_icms', label: 'Base ICMS', align: 'right', render: brl },
            { key: 'icms',    label: 'ICMS', align: 'right',
              render: v => <span style={{ color: '#79c0ff', fontWeight: 600 }}>{brl(v)}</span> },
            { key: 'total',   label: 'Total NF', align: 'right', render: brl },
          ]}
          rows={topNfs}
        />
      </Card>

      {/* ── Tributação por Item ── */}
      <SectionLabel>Tributação por Item</SectionLabel>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: '1fr 1.6fr' }}>
        <div className="flex flex-col gap-2.5">
          <Card>
            <CardTitle>Itens por Situação Tributária (saída)</CardTitle>
            <PieChart
              data={tribDist} nameKey="label" valueKey="qtd_itens" showValue formatter={fmtInt}
            />
            <p className="text-subtext text-[10px] mt-2 opacity-70">
              TbTribItem — situação tributária de saída por item (cadastro).
            </p>
          </Card>
          <Card>
            <CardTitle right="cadastro do ERP">Regras PIS/COFINS</CardTitle>
            <DataTable
              columns={[
                { key: 'descricao',   label: 'Conjunto' },
                { key: 'cst_pis',     label: 'CST PIS' },
                { key: 'aliq_pis',    label: 'Alíq. PIS',    align: 'right', render: v => pct(v, 2) },
                { key: 'cst_cofins',  label: 'CST COFINS' },
                { key: 'aliq_cofins', label: 'Alíq. COFINS', align: 'right', render: v => pct(v, 2) },
              ]}
              rows={pisCofins}
            />
          </Card>
        </div>
        <Card>
          <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
            <p className="text-[11px] text-subtext uppercase" style={{ letterSpacing: '0.8px' }}>
              Itens Vendidos no Mês × Tributação — top 200
            </p>
            <input type="text" placeholder="Buscar item, código ou marca…" value={itemBusca}
              onChange={e => { setItemBusca(e.target.value); setItemPage(0); }}
              className="w-56 px-3 py-1.5 text-xs bg-bg border border-card_border rounded-lg text-text_main placeholder-subtext focus:outline-none focus:border-accent" />
          </div>
          <DataTable
            columns={[
              { key: 'cod_item', label: 'Cód.' },
              { key: 'descricao', label: 'Item' },
              { key: 'marca', label: 'Marca' },
              { key: 'qtd_vendida', label: 'Qtd', align: 'right', render: fmtQtd },
              { key: 'valor_vendido', label: 'Valor Vendido', align: 'right', render: brl },
              { key: 'tp_trib', label: 'Tp.Trib' },
              { key: 'trib_sai', label: 'Sit.Saída' },
              { key: 'uf_trib', label: 'UF' },
            ]}
            rows={itemPageRows}
          />
          <div className="flex items-center justify-between mt-2 text-[10px] text-subtext">
            <span>{fmtInt(itensFiltrados.length)} itens{itemTotalPages > 1 && <> · pág {itemPage + 1}/{itemTotalPages}</>}</span>
            {itemTotalPages > 1 && (
              <div className="flex items-center gap-1">
                <button disabled={itemPage === 0} onClick={() => setItemPage(0)}
                  className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">«</button>
                <button disabled={itemPage === 0} onClick={() => setItemPage(p => p - 1)}
                  className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">‹</button>
                <button disabled={itemPage >= itemTotalPages - 1} onClick={() => setItemPage(p => p + 1)}
                  className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">›</button>
                <button disabled={itemPage >= itemTotalPages - 1} onClick={() => setItemPage(itemTotalPages - 1)}
                  className="px-1.5 py-0.5 rounded bg-progress_bg disabled:opacity-30 hover:text-text_main">»</button>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
