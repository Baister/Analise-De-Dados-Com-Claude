import { useState, useMemo } from 'react'
import { useFilteredDados } from '../hooks/useApi'
import KpiCard from '../components/KpiCard'
import { fmtDate } from '../utils/format'

const fmtR = v =>
  v == null ? '—' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })

function SectionLabel({ children, first }) {
  return (
    <p
      className="text-[10px] text-slate-500 uppercase mb-[7px]"
      style={{ letterSpacing: '1px', marginTop: first ? 0 : 14 }}
    >
      {children}
    </p>
  )
}

// ── DonutChart ────────────────────────────────────────────────────────────────
const DONUT_COLORS = { Concluido: '#22c55e', AVencer: '#f59e0b', Vencido: '#ef4444' }
const DONUT_LABELS = { Concluido: 'Concluído', AVencer: 'A Vencer', Vencido: 'Vencido' }
const CIRC = 2 * Math.PI * 30

function DonutChart({ data }) {
  const total = data.reduce((s, d) => s + (d.qtd || 0), 0)
  if (!total) return <p className="text-slate-500 text-sm text-center mt-4">Sem dados</p>

  let offset = 0
  const slices = data.map(d => {
    const len = (d.qtd / total) * CIRC
    const s = { ...d, len, offset }
    offset += len
    return s
  })

  return (
    <div className="flex gap-4 items-center">
      <svg width="86" height="86" viewBox="0 0 86 86" style={{ flexShrink: 0 }}>
        {slices.map(s => (
          <circle
            key={s.status}
            cx="43" cy="43" r="30"
            fill="none"
            stroke={DONUT_COLORS[s.status] || '#64748b'}
            strokeWidth="13"
            strokeDasharray={`${s.len} ${CIRC - s.len}`}
            strokeDashoffset={-s.offset}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '43px 43px' }}
          />
        ))}
        <circle cx="43" cy="43" r="22" fill="#1e293b" />
        <text x="43" y="40" textAnchor="middle" fill="#64748b" fontSize="8">total</text>
        <text x="43" y="53" textAnchor="middle" fill="#e2e8f0" fontSize="14" fontWeight="bold">
          {total}
        </text>
      </svg>
      <div className="flex flex-col gap-2 flex-1">
        {data.map(d => (
          <div key={d.status} className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: DONUT_COLORS[d.status] || '#64748b' }}
            />
            <span className="flex-1" style={{ fontSize: 11, color: '#94a3b8' }}>
              {DONUT_LABELS[d.status] || d.status}
            </span>
            <span className="font-bold" style={{ fontSize: 16, color: DONUT_COLORS[d.status] || '#e2e8f0' }}>
              {d.qtd ?? 0}
            </span>
            <span style={{ fontSize: 10, color: '#64748b' }}>{fmtR(d.valor)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── VencimentosBarChart ───────────────────────────────────────────────────────
function VencimentosBarChart({ bars, overdueSentinel, onClickable }) {
  const [hovered, setHovered] = useState(null)

  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  const allBars = []
  if (overdueSentinel) allBars.push({ ...overdueSentinel, _type: 'overdue' })
  if (bars?.length) allBars.push(...bars)

  if (!allBars.length) return (
    <p className="text-slate-500 text-sm text-center mt-6">Sem vencimentos nos próximos 30 dias</p>
  )

  const maxQtd = Math.max(...allBars.map(b => b.qtd || 0), 1)

  return (
    <div>
      <div className="flex items-end gap-1" style={{ height: 80 }}>
        {allBars.map((b, i) => {
          const isOverdue = b._type === 'overdue'
          const isToday   = b.data === todayStr
          const clickable = isOverdue || isToday

          let daysAhead = 0
          if (!isOverdue && b.data) {
            const [y, m, d] = b.data.split('-').map(Number)
            const bd = new Date(y, m - 1, d)
            daysAhead = Math.round((bd - now) / 86400000)
          }

          const color = (isOverdue || daysAhead <= 0)
            ? '#ef4444'
            : daysAhead <= 7 ? '#f59e0b' : '#22c55e'

          const h = Math.max(Math.round((b.qtd / maxQtd) * 72), 3)

          const dp = (b.data || '').split('-')
          const label = isOverdue
            ? 'Venc.'
            : isToday
              ? 'Hoje ⚡'
              : dp.length === 3 ? `${dp[2]}/${dp[1]}` : b.data

          const tooltipDate = isOverdue
            ? 'Vencidos (total)'
            : isToday ? 'Hoje' : fmtDate(b.data)

          return (
            <div
              key={isOverdue ? '_overdue' : b.data}
              className="relative flex flex-col items-center justify-end"
              style={{ flex: 1, height: '100%', gap: 3, cursor: clickable ? 'pointer' : 'default' }}
              onClick={clickable ? onClickable : undefined}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
            >
              {hovered === i && (
                <div
                  className="absolute pointer-events-none z-20"
                  style={{
                    bottom: 'calc(100% + 6px)', left: '50%', transform: 'translateX(-50%)',
                    background: '#0f172a', border: '1px solid #334155',
                    borderRadius: 6, padding: '6px 10px', whiteSpace: 'nowrap', minWidth: 110,
                  }}
                >
                  <div style={{ fontSize: 10, color: '#94a3b8', marginBottom: 2 }}>{tooltipDate}</div>
                  <div style={{ fontSize: 13, fontWeight: 700, color, marginBottom: 1 }}>
                    {b.qtd} título{b.qtd !== 1 ? 's' : ''}
                  </div>
                  <div style={{ fontSize: 10, color: '#64748b' }}>{fmtR(b.valor)}</div>
                  {clickable && (
                    <div style={{ fontSize: 9, color: '#3b82f6', marginTop: 3 }}>
                      ↓ clique para listar clientes
                    </div>
                  )}
                </div>
              )}
              <div
                style={{
                  width: '100%', height: h, background: color,
                  borderRadius: '2px 2px 0 0', flexShrink: 0,
                  filter: hovered === i ? 'brightness(1.35)' : 'none',
                  transition: 'filter 0.15s',
                }}
              />
              <div
                style={{
                  fontSize: 7.5, whiteSpace: 'nowrap', flexShrink: 0,
                  color: isToday ? '#f87171' : '#475569',
                  fontWeight: isToday ? 600 : 400,
                }}
              >
                {label}
              </div>
            </div>
          )
        })}
      </div>
      <div className="flex gap-3 mt-1.5">
        {[['#ef4444', 'Vencido'], ['#f59e0b', 'Vence ≤7d'], ['#22c55e', 'Vence 8–30d']].map(([c, l]) => (
          <div key={l} className="flex items-center gap-1" style={{ fontSize: 9, color: '#64748b' }}>
            <div style={{ width: 7, height: 7, borderRadius: 1, background: c }} />
            {l}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── DrilldownPanel ────────────────────────────────────────────────────────────
function DrilldownPanel({ title, rows, open, onClose, color, showTipo }) {
  const [filter, setFilter] = useState('')

  const filtered = useMemo(() => {
    if (!filter.trim()) return rows
    const q = filter.toLowerCase()
    return rows.filter(r => `${r.CodRedCt} ${r.NomeCli}`.toLowerCase().includes(q))
  }, [rows, filter])

  if (!open) return null

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${color}`, background: '#1e293b' }}>
      <div
        className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800/50"
        style={{ background: color + '14' }}
      >
        <span className="text-sm font-semibold" style={{ color }}>{title}</span>
        <button
          onClick={onClose}
          className="rounded text-[11px] bg-slate-900 px-2 py-0.5"
          style={{ color: '#475569' }}
        >
          ✕ fechar
        </button>
      </div>
      <div className="px-4 py-2 border-b border-slate-800/40">
        <input
          type="text"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filtrar por código ou nome do cliente…"
          className="w-full rounded text-xs outline-none placeholder-slate-500"
          style={{
            background: '#0f172a', border: '1px solid #334155', color: '#e2e8f0',
            padding: '6px 10px 6px 28px',
            backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E\")",
            backgroundRepeat: 'no-repeat', backgroundPosition: '8px center',
          }}
        />
      </div>
      <div style={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto' }}>
        <table className="w-full" style={{ fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Cód. · Cliente', 'Nº Título', ...(showTipo ? ['Tipo'] : []), 'Valor',
                ...(showTipo ? [] : ['Vencimento']), showTipo ? 'Situação' : 'Falta/Atraso'
              ].map(h => (
                <th
                  key={h}
                  className="px-3 py-2 text-left"
                  style={{ fontSize: 9, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!filtered.length ? (
              <tr>
                <td colSpan={showTipo ? 5 : 5} className="px-3 py-4 text-center text-slate-500 text-xs">
                  Nenhum título encontrado
                </td>
              </tr>
            ) : filtered.map(r => {
              const dias = r.dias ?? 0
              const chipColor = dias > 0 ? '#f87171' : dias < 0 ? '#60a5fa' : '#fbbf24'
              const chipBg    = dias > 0 ? 'rgba(239,68,68,0.15)' : dias < 0 ? 'rgba(34,197,94,0.15)' : 'rgba(245,158,11,0.2)'
              const chipText  = dias > 0 ? `${dias} dias` : dias < 0 ? `${-dias} dias` : 'Hoje'
              const receita   = (r.Receita || '').toUpperCase()
              const isCartao  = receita.includes('CARTAO')
              const tipoColor = isCartao ? '#c084fc' : '#60a5fa'
              const tipoBg    = isCartao ? 'rgba(168,85,247,0.15)' : 'rgba(59,130,246,0.15)'
              const tipoLabel = isCartao ? 'Cartão' : 'Boleto'

              return (
                <tr
                  key={`${r.CodRedCt}-${r.NrDoc}`}
                  style={{ borderBottom: '1px solid #0f172a' }}
                  className="hover:bg-slate-800/20"
                >
                  <td className="px-3 py-1.5" style={{ verticalAlign: 'middle' }}>
                    <div className="font-medium" style={{ color: '#e2e8f0' }}>
                      {r.CodRedCt && (
                        <span
                          className="inline-block font-bold rounded mr-1.5"
                          style={{ fontSize: 9, background: '#0f172a', color: '#94a3b8', padding: '1px 5px', border: '1px solid #334155' }}
                        >
                          {r.CodRedCt}
                        </span>
                      )}
                      {r.NomeCli}
                    </div>
                  </td>
                  <td className="px-3 py-1.5" style={{ fontSize: 11, color: '#64748b' }}>{r.NrDoc}</td>
                  {showTipo && (
                    <td className="px-3 py-1.5">
                      <span style={{ fontSize: 10, background: tipoBg, color: tipoColor, padding: '1px 6px', borderRadius: 4 }}>
                        {tipoLabel}
                      </span>
                    </td>
                  )}
                  <td className="px-3 py-1.5 text-right" style={{ fontSize: 11, color: '#94a3b8' }}>
                    {fmtR(r.VlrTitulo)}
                  </td>
                  {!showTipo && (
                    <td className="px-3 py-1.5" style={{ fontSize: 11, color: '#94a3b8' }}>
                      {fmtDate(r.DtVcto)}
                    </td>
                  )}
                  <td className="px-3 py-1.5 text-right">
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 9999,
                      background: chipBg, color: chipColor, whiteSpace: 'nowrap',
                    }}>
                      {showTipo ? 'Vence Hoje' : chipText}
                    </span>
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

// ── FocoSection ───────────────────────────────────────────────────────────────
function FocoSection({ icon, title, sub, stats, idVenc, idAven, openPanel, togglePanel, color, chips, recebidoMes }) {
  const isVencOpen = openPanel === idVenc
  const isAvenOpen = openPanel === idAven

  return (
    <div className="rounded-lg p-4" style={{ background: '#1e293b' }}>
      <div className="flex items-center gap-2 mb-3">
        <div
          className="flex items-center justify-center rounded-md"
          style={{ width: 26, height: 26, background: color + '26', fontSize: 13, flexShrink: 0 }}
        >
          {icon}
        </div>
        <div>
          <div className="font-semibold" style={{ fontSize: 12, color }}>{title}</div>
          <div style={{ fontSize: 10, color: '#64748b' }}>{sub}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="rounded-md p-2.5" style={{ background: '#0f172a' }}>
          <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 3 }}>Em Aberto</div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1, color }}>{stats.qtd_total ?? 0}</div>
          <div style={{ fontSize: 9, color: '#64748b', marginTop: 2 }}>{fmtR(stats.valor_total)}</div>
        </div>

        <div
          className="rounded-md p-2.5 cursor-pointer"
          style={{ background: '#0f172a', outline: isVencOpen ? '1px solid #ef4444' : 'none', transition: 'outline 0.1s' }}
          onClick={() => togglePanel(idVenc)}
        >
          <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 3 }}>Vencidos ⚡</div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1, color: '#f87171' }}>{stats.qtd_vencidos ?? 0}</div>
          <div style={{ fontSize: 9, color: '#3b82f6', marginTop: 2 }}>↓ ver clientes</div>
        </div>

        <div
          className="rounded-md p-2.5 cursor-pointer"
          style={{ background: '#0f172a', outline: isAvenOpen ? `1px solid ${color}` : 'none', transition: 'outline 0.1s' }}
          onClick={() => togglePanel(idAven)}
        >
          <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 3 }}>A Vencer 30d ⚡</div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1, color: '#fbbf24' }}>{stats.qtd_a_vencer ?? 0}</div>
          <div style={{ fontSize: 9, color: '#3b82f6', marginTop: 2 }}>↓ ver clientes</div>
        </div>

        <div className="rounded-md p-2.5" style={{ background: '#0f172a' }}>
          <div style={{ fontSize: 9, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 3 }}>Recebido no Mês</div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.1, color: '#22c55e' }}>{recebidoMes ?? 0}</div>
          <div style={{ fontSize: 9, color: '#64748b', marginTop: 2 }}>títulos recebidos</div>
        </div>
      </div>

      <div style={{ height: 1, background: '#0f172a', margin: '8px 0' }} />

      <div className="flex gap-1.5 flex-wrap">
        {chips.length
          ? chips.map((c, i) => (
              <span key={i} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 4, background: c.bg, color: c.color }}>
                {c.text}
              </span>
            ))
          : <span style={{ fontSize: 10, color: '#334155' }}>—</span>
        }
      </div>
    </div>
  )
}

// ── LimiteCreditoTable ────────────────────────────────────────────────────────
function LimiteCreditoTable({ rows }) {
  const [filter, setFilter] = useState('')
  const filtered = useMemo(() => {
    if (!filter.trim()) return rows ?? []
    const q = filter.toLowerCase()
    return (rows ?? []).filter(r =>
      String(r.CodRedCt ?? '').toLowerCase().includes(q) ||
      String(r.NomeFantCli ?? '').toLowerCase().includes(q)
    )
  }, [rows, filter])

  return (
    <div className="rounded-lg p-4" style={{ background: '#1e293b' }}>
      <div className="flex justify-between items-center mb-2.5">
        <span style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
          Utilização por Cliente
        </span>
        <span style={{ fontSize: 10, color: '#3b82f6', background: 'rgba(59,130,246,0.1)', padding: '2px 8px', borderRadius: 4 }}>
          TbCli ⟶ TbLimCredCli · ValLimCred1
        </span>
      </div>
      <div className="mb-2.5">
        <input
          type="text"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="Filtrar por código ou nome do cliente…"
          className="w-full rounded text-xs outline-none placeholder-slate-500"
          style={{
            background: '#0f172a', border: '1px solid #334155', color: '#e2e8f0',
            padding: '6px 10px 6px 28px',
            backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E\")",
            backgroundRepeat: 'no-repeat', backgroundPosition: '8px center',
          }}
        />
      </div>
      <div style={{ overflowX: 'auto', maxHeight: 288, overflowY: 'auto' }}>
        <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr>
              {['Cliente', 'Limite', 'Utilizado', 'Disponível', 'Uso %', 'Status'].map(h => (
                <th key={h} className="text-left pb-2 pr-2"
                  style={{ fontSize: 9, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px', fontWeight: 600 }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!filtered.length ? (
              <tr>
                <td colSpan={6} className="py-6 text-center text-xs" style={{ color: '#475569' }}>
                  {filter.trim() ? 'Nenhum cliente encontrado para este filtro' : 'Nenhum cliente com limite de crédito cadastrado para boleto'}
                </td>
              </tr>
            ) : filtered.map(r => {
              const pct = r.pct_utilizado ?? 0
              const barColor = pct >= 90 ? '#ef4444' : pct >= 70 ? '#f59e0b' : '#22c55e'
              const badge = pct >= 90
                ? { bg: 'rgba(239,68,68,0.15)',  color: '#ef4444', label: 'EXCEDIDO' }
                : pct >= 70
                  ? { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', label: `RISCO · ${pct.toFixed(1)}%` }
                  : { bg: 'rgba(34,197,94,0.15)',  color: '#22c55e', label: `OK · ${pct.toFixed(1)}%` }
              return (
                <tr key={r.CodRedCt} style={{ borderBottom: '1px solid #0f172a' }}>
                  <td className="py-1.5 pr-2 font-medium" style={{ color: '#e2e8f0' }}>{r.NomeFantCli}</td>
                  <td className="py-1.5 pr-2" style={{ fontSize: 11, color: '#94a3b8' }}>{fmtR(r.limite_credito)}</td>
                  <td className="py-1.5 pr-2" style={{ fontSize: 11, color: barColor }}>{fmtR(r.utilizado)}</td>
                  <td className="py-1.5 pr-2" style={{ fontSize: 11, color: r.livre > 0 ? '#4ade80' : '#f87171' }}>{fmtR(r.livre)}</td>
                  <td className="py-1.5 pr-2" style={{ width: 80 }}>
                    <div style={{ height: 5, borderRadius: 3, background: '#0f172a', overflow: 'hidden' }}>
                      <div style={{ height: 5, borderRadius: 3, background: barColor, width: `${Math.min(pct, 100)}%` }} />
                    </div>
                  </td>
                  <td className="py-1.5">
                    <span style={{ fontSize: 9, padding: '2px 7px', borderRadius: 9999, fontWeight: 600, background: badge.bg, color: badge.color }}>
                      {badge.label}
                    </span>
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

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Financeiro({ refreshTrigger }) {
  const { data, loading, error, isEmpty } = useFilteredDados('financeiro', {}, refreshTrigger)
  const [openPanel, setOpenPanel] = useState(null)

  const qtd_total_aberto  = data?.qtd_total_aberto  ?? 0
  const qtd_vencidos      = data?.qtd_vencidos      ?? 0
  const qtd_a_vencer      = data?.qtd_a_vencer      ?? 0
  const qtd_recebido_mes  = data?.qtd_recebido_mes  ?? 0
  const qtd_recebido_bol  = data?.qtd_recebido_bol  ?? 0
  const qtd_recebido_car  = data?.qtd_recebido_car  ?? 0
  const donutData         = (data?.donut_status ?? []).filter(d => d.status !== 'Concluido')
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

  const emRisco = limiteRows.filter(r => (r.pct_utilizado ?? 0) >= 90).length
  const boletoChips = emRisco > 0
    ? [{ text: `${emRisco} em risco >90%`, bg: 'rgba(245,158,11,0.15)', color: '#f59e0b' }]
    : []

  const ticketMedio = (cartao.qtd_total || 0) > 0 ? (cartao.valor_total || 0) / cartao.qtd_total : 0
  const cartaoChips = ticketMedio > 0
    ? [{ text: `${fmtR(ticketMedio)} ticket médio`, bg: 'rgba(168,85,247,0.15)', color: '#c084fc' }]
    : []

  if (loading && !data) return (
    <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
      Carregando dados financeiros…
    </div>
  )
  if (error && !data) return (
    <div className="flex items-center justify-center h-64 text-red-400 text-sm">
      Erro ao carregar dados: {error}
    </div>
  )
  if (isEmpty) return (
    <div className="flex items-center justify-center h-64 text-slate-500 text-sm">
      <div className="text-center space-y-1">
        <p>Bot Financeiro está processando dados…</p>
        <p className="text-xs opacity-60">A página atualiza automaticamente quando concluir.</p>
      </div>
    </div>
  )

  return (
    <div className="p-4">

      {/* ── Visão Geral ──────────────────────────────────────────── */}
      <SectionLabel first>Visão Geral — Contas a Receber</SectionLabel>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
        <KpiCard label="Total a Receber"   value={String(qtd_total_aberto)} sub="títulos em aberto"  variant="default" topBorder="#3b82f6" />
        <KpiCard label="Títulos Vencidos"  value={String(qtd_vencidos)}     sub="em atraso"          variant="error"   topBorder="#ef4444" />
        <KpiCard label="Próximos a Vencer" value={String(qtd_a_vencer)}     sub="próximos 30 dias"   variant="warning" topBorder="#f59e0b" />
        <KpiCard label="Recebido no Mês"   value={String(qtd_recebido_mes)} sub="títulos recebidos"  variant="success" topBorder="#22c55e" />
      </div>

      {/* ── Análise ──────────────────────────────────────────────── */}
      <SectionLabel>Análise</SectionLabel>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: '1fr 1.7fr' }}>
        <div className="rounded-lg p-4" style={{ background: '#1e293b' }}>
          <p className="mb-3" style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
            Status dos Títulos
          </p>
          <DonutChart data={donutData} />
        </div>
        <div className="rounded-lg p-4" style={{ background: '#1e293b' }}>
          <p className="mb-3" style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.8px' }}>
            Vencimentos — Próximos 30 Dias (hover = qtd · clique Hoje = lista)
          </p>
          <VencimentosBarChart
            bars={venc30d}
            onClickable={() => togglePanel('hoje-venc')}
          />
        </div>
      </div>

      {/* ── Drill-down Hoje ───────────────────────────────────────── */}
      {openPanel === 'hoje-venc' && (
        <div className="mt-2.5">
          <DrilldownPanel
            title="⚡ Vencimentos de Hoje — Todos os Clientes"
            rows={hojeVenc}
            open
            onClose={() => setOpenPanel(null)}
            color="#f59e0b"
            showTipo
          />
        </div>
      )}

      {/* ── Foco — Boleto & Cartão ────────────────────────────────── */}
      <SectionLabel>Foco — Boleto &amp; Cartão</SectionLabel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
        <FocoSection
          icon="🧾"
          title="Boleto Local"
          sub="CodPlanoVnd 06, 16-18, 23-24, 30, 32-51, 54"
          stats={boleto}
          idVenc="bol-venc"
          idAven="bol-aven"
          openPanel={openPanel}
          togglePanel={togglePanel}
          color="#3b82f6"
          chips={boletoChips}
          recebidoMes={qtd_recebido_bol}
        />
        <FocoSection
          icon="💳"
          title="Cartão"
          sub="CodPlanoVnd 29"
          stats={cartao}
          idVenc="car-venc"
          idAven="car-aven"
          openPanel={openPanel}
          togglePanel={togglePanel}
          color="#a855f7"
          chips={cartaoChips}
          recebidoMes={qtd_recebido_car}
        />
      </div>

      {/* ── Drill-downs ───────────────────────────────────────────── */}
      <div className="mt-2.5 space-y-2.5">
        <DrilldownPanel title="🧾 Boleto — Títulos a Vencer"  rows={bolAven} open={openPanel === 'bol-aven'} onClose={() => setOpenPanel(null)} color="#3b82f6" />
        <DrilldownPanel title="🔴 Boleto — Títulos Vencidos"  rows={bolVenc} open={openPanel === 'bol-venc'} onClose={() => setOpenPanel(null)} color="#ef4444" />
        <DrilldownPanel title="💳 Cartão — Títulos a Vencer"  rows={carAven} open={openPanel === 'car-aven'} onClose={() => setOpenPanel(null)} color="#a855f7" />
        <DrilldownPanel title="🔴 Cartão — Títulos Vencidos"  rows={carVenc} open={openPanel === 'car-venc'} onClose={() => setOpenPanel(null)} color="#ef4444" />
      </div>

      {/* ── Limite de Crédito — Clientes Boleto ──────────────────── */}
      <SectionLabel>Limite de Crédito — Clientes Boleto</SectionLabel>
      <LimiteCreditoTable rows={limiteRows} />

      {data?.ultimo_update && (
        <p className="mt-3 text-center" style={{ fontSize: 10, color: '#334155' }}>
          Atualizado: {data.ultimo_update}
        </p>
      )}

    </div>
  )
}
