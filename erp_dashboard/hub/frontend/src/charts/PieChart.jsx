import {
  PieChart as RC, Pie, Cell, Tooltip, ResponsiveContainer,
} from 'recharts';
import { brl } from '../utils/format';

const COLORS  = ['#1f6feb', '#238636', '#d29922', '#da3633', '#8b949e', '#a371f7'];
const TOOLTIP = {
  contentStyle: { background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12, color: '#e6edf3' },
  labelStyle:   { color: '#e6edf3' },
  itemStyle:    { color: '#e6edf3' },
};

// showValue=true → legenda mostra "Nome · R$XXk"
// formatter: função de formatação do valor (padrão: brl)
// colors: paleta customizada (padrão: COLORS) — ex. cores semânticas A/B/C
// tooltipContext: { title, formula, extra: [{key, label, formatter}] }
//   → ativa tooltip customizado com contexto de como o valor foi calculado
export default function PieChart({
  data, nameKey, valueKey, showValue = false, formatter, height = 200, highlightKey = null,
  tooltipContext = null, colors = COLORS,
}) {
  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-[200px] text-subtext text-sm">
        Sem dados
      </div>
    );
  }
  const fmt = formatter || brl;

  const total = data.reduce((s, d) => s + (d[valueKey] ?? 0), 0);

  const customTooltip = tooltipContext ? ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const item = payload[0].payload;
    const val  = item[valueKey] ?? 0;
    const pct  = total > 0 ? (val / total * 100).toFixed(1) : '0.0';
    return (
      <div style={{
        background: '#1c2128', border: '1px solid #30363d', borderRadius: 6,
        fontSize: 12, padding: '10px 14px', color: '#e6edf3', maxWidth: 280,
        boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
      }}>
        <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13, borderBottom: '1px solid #30363d', paddingBottom: 6 }}>
          {item[nameKey]}
        </div>
        <div style={{ marginBottom: 4 }}>
          <span style={{ color: '#8b949e' }}>{tooltipContext.title}: </span>
          <span style={{ fontWeight: 600 }}>{fmt(val)}</span>
          <span style={{ color: '#6e7681', marginLeft: 8, fontSize: 11 }}>{pct}% do total</span>
        </div>
        {tooltipContext.extra?.map(ex => (
          <div key={ex.key} style={{ color: '#8b949e', marginBottom: 2 }}>
            {ex.label}:{' '}
            <span style={{ color: '#e6edf3' }}>
              {ex.formatter ? ex.formatter(item[ex.key] ?? 0) : (item[ex.key] ?? '—')}
            </span>
          </div>
        ))}
        {tooltipContext.formula && (
          <div style={{ color: '#6e7681', marginTop: 8, fontSize: 10, borderTop: '1px solid #21262d', paddingTop: 6 }}>
            {tooltipContext.formula}
          </div>
        )}
      </div>
    );
  } : null;

  return (
    <div style={{ height }} className="flex items-center gap-4">
      {/* Pie — largura fixa à esquerda, nunca invade a legenda */}
      <div className="flex-shrink-0" style={{ width: 160, height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RC>
            <Pie
              data={data}
              nameKey={nameKey}
              dataKey={valueKey}
              innerRadius={45}
              outerRadius={72}
              paddingAngle={2}
            >
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={colors[i % colors.length]}
                  fillOpacity={highlightKey ? (entry[nameKey] === highlightKey ? 1 : 0.35) : 1}
                />
              ))}
            </Pie>
            {customTooltip
              ? <Tooltip content={customTooltip} />
              : <Tooltip {...TOOLTIP} formatter={v => [fmt(v)]} />
            }
          </RC>
        </ResponsiveContainer>
      </div>

      {/* Legenda — ocupa o espaço restante à direita */}
      <ul
        className="flex-1 flex flex-col gap-2 text-[10px] overflow-y-auto pr-1"
        style={{ maxHeight: height - 16 }}
      >
        {data.map((entry, i) => (
          <li key={i} className="flex items-start gap-1.5">
            <span
              className="w-2 h-2 rounded-sm flex-shrink-0 inline-block mt-[1px]"
              style={{ background: colors[i % colors.length] }}
            />
            <span className="text-subtext leading-snug">
              {entry[nameKey]}
              {showValue && (
                <> · <span className="text-text_main font-bold">{fmt(entry[valueKey])}</span></>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
