import { useState, useMemo } from 'react'
import { useFilteredDados } from '../hooks/useApi'
import KpiCard from '../components/KpiCard'
import { fmtDate } from '../utils/format'

// ── Formatters ──────────────────────────────────────────────────────────────
const fmtR = v =>
  v == null ? '—' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

// ── DonutChart (SVG pure) ───────────────────────────────────────────────────
const DONUT_COLORS = { Concluido: '#22c55e', AVencer: '#3b82f6', Vencido: '#ef4444' }
const DONUT_LABELS = { Concluido: 'Concluído', AVencer: 'A Vencer', Vencido: 'Vencido' }
const CIRC = 2 * Math.PI * 40  // r=40

function DonutChart({ data }) {
  const total = data.reduce((s, d) => s + (d.qtd || 0), 0)
  if (!total) return (
    <p className="text-subtext text-sm text-center mt-4">Sem dados</p>
  )

  let offset = 0
  const slices = data.map(d => {
    const len = (d.qtd / total) * CIRC
    const s = { ...d, len, offset }
    offset += len
    return s
  })

  return (
    <div className="flex gap-4 items-center">
      <svg width="100" height="100" viewBox="0 0 100 100" style={{ flexShrink: 0 }}>
        {slices.map(s => (
          <circle
            key={s.status}
            cx="50" cy="50" r="40"
            fill="none"
            stroke={DONUT_COLORS[s.status] || '#64748b'}
            strokeWidth="16"
            strokeDasharray={`${s.len} ${CIRC - s.len}`}
            strokeDashoffset={-s.offset}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '50px 50px' }}
          />
        ))}
        <circle cx="50" cy="50" r="32" fill="#1e293b" />
        <text x="50" y="54" textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight="bold">
          {total}
        </text>
      </svg>
      <div className="flex flex-col gap-2 flex-1">
        {data.map(d => (
          <div key={d.status} className="flex items-center gap-2">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{ background: DONUT_COLORS[d.status] || '#64748b' }}
            />
            <span className="text-[11px] text-subtext flex-1">
              {DONUT_LABELS[d.status] || d.status}
            </span>
            <span
              className="text-sm font-bold"
              style={{ color: DONUT_COLORS[d.status] || '#e2e8f0' }}
            >
              {d.qtd ?? 0}
            </span>
            <span className="text-[10px] text-subtext ml-1">{fmtR(d.valor)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── VencimentosBarChart ──────────────────────────────────────────────────────
function VencimentosBarChart({ bars, onTodayClick }) {
  const [tooltip, setTooltip] = useState(null)

  if (!bars?.length) return (
    <p className="text-subtext text-sm text-center mt-6">
      Sem vencimentos nos próximos 30 dias
    </p>
  )

  const d = new Date()
  const todayStr = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  const maxQtd = Math.max(...bars.map(b => b.qtd || 0), 1)

  return (
    <div className="relative">
      <div className="flex items-end gap-1" style={{ height: 80 }}>
        {bars.map(b => {
          const isToday = b.data === todayStr
          const h = Math.max(Math.round((b.qtd / maxQtd) * 72), 3)
          const color = isToday ? '#f59e0b' : '#3b82f6'
          const parts = b.data.split('-')
          const label = parts.length === 3 ? `${parts[2]}/${parts[1]}` : b.data
          return (
            <div
              key={b.data}
              className="flex-1 flex flex-col items-center justify-end cursor-pointer relative"
              style={{ height: '100%' }}
              onClick={isToday ? onTodayClick : undefined}
              onMouseEnter={() => setTooltip(b)}
              onMouseLeave={() => setTooltip(null)}
              title={isToday ? 'Clique para ver clientes com vencimento hoje' : undefined}
            >
              <div
                style={{
                  height: h,
                  background: color,
                  width: '100%',
                  borderRadius: '3px 3px 0 0',
                  opacity: isToday ? 1 : 0.7,
                }}
              />
              {tooltip === b && (
                <div
                  className="absolute bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-white pointer-events-none z-10"
                  style={{ bottom: '100%', left: '50%', transform: 'translateX(-50%)', whiteSpace: 'nowrap', marginBottom: 4 }}
                >
                  <div className="font-medium">{label}</div>
                  <div>{b.qtd} título{b.qtd !== 1 ? 's' : ''}</div>
                  <div>{fmtR(b.valor)}</div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      {/* X-axis labels */}
      <div className="flex mt-1" style={{ gap: '4px' }}>
        {bars.map((b, i) => {
          const show = i === 0 || i === Math.floor(bars.length / 2) || i === bars.length - 1
          const parts = b.data.split('-')
          return (
            <div
              key={b.data}
              className="flex-1 text-center"
              style={{ fontSize: 9, color: '#475569' }}
            >
              {show && parts.length === 3 ? `${parts[2]}/${parts[1]}` : ''}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── DrilldownPanel ───────────────────────────────────────────────────────────
function DrilldownPanel({ title, rows, open, onClose, color }) {
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    if (!filter.trim()) return rows
    const q = filter.toLowerCase()
    return rows.filter(r =>
      `${r.CodRedCt} ${r.NomeCli}`.toLowerCase().includes(q)
    )
  }, [rows, filter])

  if (!open) return null

  return (
    <div
      className="border rounded-lg overflow-hidden"
      style={{ borderColor: color, background: '#0f172a' }}
    >
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ background: color + '18' }}
      >
        <span className="text-sm font-semibold" style={{ color }}>{title}</span>
        <button
          onClick={onClose}
          className="text-subtext text-xs hover:text-text_main transition-colors"
        >
          ✕ fechar
        </button>
      </div>
      <div className="px-4 py-2 border-b border-slate-800">
        <input
          type="text"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filtrar por código ou nome do cliente…"
          className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-blue-500 placeholder-slate-500"
        />
      </div>
      <div className="overflow-x-auto max-h-80 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="px-3 py-2 text-left text-slate-400 font-semibold">Cód. · Cliente</th>
              <th className="px-3 py-2 text-left text-slate-400 font-semibold">Nº Título</th>
              <th className="px-3 py-2 text-right text-slate-400 font-semibold">Valor</th>
              <th className="px-3 py-2 text-left text-slate-400 font-semibold">Vencimento</th>
              <th className="px-3 py-2 text-right text-slate-400 font-semibold">Falta/Atraso</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-slate-500">
                  Nenhum título encontrado
                </td>
              </tr>
            ) : filtered.map(r => (
              <tr key={`${r.CodRedCt}-${r.NrDoc}`} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                <td className="px-3 py-2 text-slate-200">
                  {r.CodRedCt && (
                    <span
                      className="inline-block text-[9px] font-bold bg-slate-900 text-slate-400 px-1.5 py-0.5 rounded mr-1.5"
                      style={{ border: '1px solid #334155' }}
                    >
                      {r.CodRedCt}
                    </span>
                  )}
                  {r.NomeCli}
                </td>
                <td className="px-3 py-2 text-slate-300">{r.NrDoc}</td>
                <td className="px-3 py-2 text-right text-slate-200 font-medium">
                  {fmtR(r.VlrTitulo)}
                </td>
                <td className="px-3 py-2 text-slate-300">{fmtDate(r.DtVcto)}</td>
                <td className="px-3 py-2 text-right">
                  <span style={{
                    color: r.dias > 0 ? '#f87171' : r.dias < 0 ? '#60a5fa' : '#fbbf24'
                  }}>
                    {r.dias > 0
                      ? `${r.dias}d atraso`
                      : r.dias < 0
                        ? `${-r.dias}d restantes`
                        : 'hoje'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── StatChip ─────────────────────────────────────────────────────────────────
function StatChip({ label, value, color }) {
  return (
    <div className="bg-slate-900 rounded-lg px-3 py-2 flex flex-col">
      <span className="text-[9px] text-slate-500 uppercase tracking-wider mb-0.5">{label}</span>
      <span className="text-sm font-bold" style={{ color: color || '#e2e8f0' }}>{value}</span>
    </div>
  )
}

// ── FocoSection ───────────────────────────────────────────────────────────────
function FocoSection({ title, stats, idVenc, idAven, openPanel, togglePanel, color }) {
  const isVencOpen = openPanel === idVenc
  const isAvenOpen = openPanel === idAven

  return (
    <div className="bg-card border border-card_border rounded-lg p-4 space-y-3">
      <p className="text-[10px] text-subtext uppercase tracking-widest">{title}</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <StatChip label="Total Títulos" value={stats.qtd_total ?? 0}    color="#e2e8f0" />
        <StatChip label="Valor Total"   value={fmtR(stats.valor_total)} color={color}  />
        <StatChip label="Vencidos"      value={stats.qtd_vencidos ?? 0} color="#f87171" />
        <StatChip label="A Vencer"      value={stats.qtd_a_vencer ?? 0} color="#60a5fa" />
      </div>
      <div className="flex gap-3">
        <button
          onClick={() => togglePanel(idVenc)}
          className="flex-1 text-xs py-2 rounded-lg border transition-all font-medium"
          style={{
            borderColor: isVencOpen ? '#ef4444' : '#334155',
            color:        isVencOpen ? '#f87171' : '#94a3b8',
            background:   isVencOpen ? '#ef444415' : 'transparent',
          }}
        >
          Vencidos ⚡ <span className="ml-1 opacity-70">({stats.qtd_vencidos ?? 0})</span>
        </button>
        <button
          onClick={() => togglePanel(idAven)}
          className="flex-1 text-xs py-2 rounded-lg border transition-all font-medium"
          style={{
            borderColor: isAvenOpen ? color : '#334155',
            color:        isAvenOpen ? color : '#94a3b8',
            background:   isAvenOpen ? color + '20' : 'transparent',
          }}
        >
          A Vencer 30d ⚡ <span className="ml-1 opacity-70">({stats.qtd_a_vencer ?? 0})</span>
        </button>
      </div>
    </div>
  )
}

// ── LimiteCreditoTable ────────────────────────────────────────────────────────
function LimiteCreditoTable({ rows }) {
  if (!rows?.length) return null

  return (
    <div className="bg-card border border-card_border rounded-lg p-4">
      <p className="text-[10px] text-subtext uppercase tracking-widest mb-3">
        Limite de Crédito — Boleto ({rows.length})
      </p>
      <div className="overflow-x-auto max-h-72 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-800">
              <th className="px-3 py-2 text-left text-slate-400 font-semibold">Cód. · Cliente</th>
              <th className="px-3 py-2 text-right text-slate-400 font-semibold">Limite</th>
              <th className="px-3 py-2 text-right text-slate-400 font-semibold">Utilizado</th>
              <th className="px-3 py-2 text-right text-slate-400 font-semibold">Livre</th>
              <th className="px-3 py-2 text-left text-slate-400 font-semibold" style={{ minWidth: 100 }}>
                Utilização
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const pct = r.pct_utilizado ?? 0
              const barColor = pct >= 90 ? '#ef4444' : pct >= 70 ? '#f59e0b' : '#22c55e'
              return (
                <tr key={r.CodRedCt} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-3 py-2 text-slate-200">
                    {r.CodRedCt && (
                      <span
                        className="inline-block text-[9px] font-bold bg-slate-900 text-slate-400 px-1.5 py-0.5 rounded mr-1.5"
                        style={{ border: '1px solid #334155' }}
                      >
                        {r.CodRedCt}
                      </span>
                    )}
                    {r.NomeFantCli}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-300">{fmtR(r.limite_credito)}</td>
                  <td className="px-3 py-2 text-right font-medium" style={{ color: barColor }}>
                    {fmtR(r.utilizado)}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-300">{fmtR(r.livre)}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          style={{
                            width: `${Math.min(pct, 100)}%`,
                            height: '100%',
                            background: barColor,
                            borderRadius: 9999,
                          }}
                        />
                      </div>
                      <span className="text-[10px]" style={{ color: barColor }}>
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Financeiro({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('financeiro', {}, refreshTrigger)
  const [openPanel, setOpenPanel] = useState(null)

  const qtd_total_aberto = data?.qtd_total_aberto ?? 0
  const qtd_vencidos     = data?.qtd_vencidos     ?? 0
  const qtd_a_vencer     = data?.qtd_a_vencer     ?? 0
  const qtd_recebido_mes = data?.qtd_recebido_mes ?? 0
  const donutData        = data?.donut_status     ?? []
  const venc30d          = data?.vencimentos_30d  ?? []
  const boleto           = data?.boleto           ?? {}
  const cartao           = data?.cartao           ?? {}
  const bolVenc          = data?.bol_vencidos     ?? []
  const bolAven          = data?.bol_a_vencer     ?? []
  const carVenc          = data?.car_vencidos     ?? []
  const carAven          = data?.car_a_vencer     ?? []
  const hojeVenc         = data?.hoje_vencidos    ?? []
  const limiteRows       = data?.limite_credito   ?? []

  const togglePanel = id => setOpenPanel(p => p === id ? null : id)

  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-subtext text-sm">
      Carregando dados financeiros…
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
        <p>Bot Financeiro está processando dados…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  )

  return (
    <div className="p-6 space-y-5">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-text_main">Contas a Receber</h1>
        {data?.ultimo_update && (
          <span className="text-subtext text-xs">Atualizado: {data.ultimo_update}</span>
        )}
      </div>

      {/* ── KPI Cards ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          label="Total a Receber"
          value={String(qtd_total_aberto)}
          sub="títulos em aberto"
          variant="default"
          topBorder="#3b82f6"
        />
        <KpiCard
          label="Títulos Vencidos"
          value={String(qtd_vencidos)}
          sub="em atraso"
          variant="error"
          topBorder="#ef4444"
        />
        <KpiCard
          label="Próximos a Vencer"
          value={String(qtd_a_vencer)}
          sub="nos próximos 30 dias"
          variant="warning"
          topBorder="#f59e0b"
        />
        <KpiCard
          label="Recebido no Mês"
          value={String(qtd_recebido_mes)}
          sub="títulos quitados"
          variant="success"
          topBorder="#22c55e"
        />
      </div>

      {/* ── Charts Row ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 bg-card border border-card_border rounded-lg p-4">
          <p className="text-[10px] text-subtext uppercase tracking-widest mb-3">
            Status dos Títulos
          </p>
          <DonutChart data={donutData} />
        </div>
        <div className="lg:col-span-3 bg-card border border-card_border rounded-lg p-4">
          <p className="text-[10px] text-subtext uppercase tracking-widest mb-3">
            Vencimentos — Próximos 30 Dias
          </p>
          <VencimentosBarChart
            bars={venc30d}
            onTodayClick={() => togglePanel('hoje-venc')}
          />
        </div>
      </div>

      {/* ── Drill-down: Hoje ───────────────────────────────────────────── */}
      <DrilldownPanel
        title="⚡ Vencimentos Hoje — Todos os Tipos"
        rows={hojeVenc}
        open={openPanel === 'hoje-venc'}
        onClose={() => setOpenPanel(null)}
        color="#f59e0b"
      />

      {/* ── Foco Boleto ────────────────────────────────────────────────── */}
      <FocoSection
        title="🧾 Foco — Boleto"
        stats={boleto}
        idVenc="bol-venc"
        idAven="bol-aven"
        openPanel={openPanel}
        togglePanel={togglePanel}
        color="#3b82f6"
      />
      <DrilldownPanel
        title="🔴 Boleto — Títulos Vencidos"
        rows={bolVenc}
        open={openPanel === 'bol-venc'}
        onClose={() => setOpenPanel(null)}
        color="#ef4444"
      />
      <DrilldownPanel
        title="🧾 Boleto — Títulos a Vencer"
        rows={bolAven}
        open={openPanel === 'bol-aven'}
        onClose={() => setOpenPanel(null)}
        color="#3b82f6"
      />

      {/* ── Foco Cartão ─────────────────────────────────────────────────── */}
      <FocoSection
        title="💳 Foco — Cartão"
        stats={cartao}
        idVenc="car-venc"
        idAven="car-aven"
        openPanel={openPanel}
        togglePanel={togglePanel}
        color="#a855f7"
      />
      <DrilldownPanel
        title="🔴 Cartão — Títulos Vencidos"
        rows={carVenc}
        open={openPanel === 'car-venc'}
        onClose={() => setOpenPanel(null)}
        color="#ef4444"
      />
      <DrilldownPanel
        title="💳 Cartão — Títulos a Vencer"
        rows={carAven}
        open={openPanel === 'car-aven'}
        onClose={() => setOpenPanel(null)}
        color="#a855f7"
      />

      {/* ── Limite de Crédito ───────────────────────────────────────────── */}
      <LimiteCreditoTable rows={limiteRows} />

    </div>
  )
}
