import {
  BarChart as RC, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LabelList, Legend,
} from 'recharts';

const TOOLTIP_STYLE = {
  contentStyle: { background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 },
  labelStyle:   { color: '#e6edf3' },
  itemStyle:    { color: '#8b949e' },
};
const TICK   = { fill: '#8b949e', fontSize: 10 };
const GRID   = { strokeDasharray: '3 3', stroke: '#30363d' };
const COLORS = ['#1f6feb', '#238636', '#d29922', '#da3633', '#8b949e'];

function Empty() {
  return (
    <div className="flex items-center justify-center h-[220px] text-subtext text-sm">
      Sem dados
    </div>
  );
}

// bars: [{ key, label?, formatter? }]
// horizontal: inverte eixos para barras horizontais
// showLabels: mostra valor ao final da barra (branco negrito)
// stacked: empilha múltiplas barras
export default function BarChart({
  data, xKey, bars = [], horizontal = false, showLabels = false,
  stacked = false, colors = COLORS, height = 220,
}) {
  if (!data?.length || !bars.length) return <Empty />;

  const fmt = bars[0]?.formatter;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RC
        data={data}
        layout={horizontal ? 'vertical' : 'horizontal'}
        margin={{ top: 8, right: showLabels ? 70 : 16, bottom: 8, left: 8 }}
      >
        <CartesianGrid {...GRID} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={TICK} tickFormatter={fmt} />
            <YAxis type="category" dataKey={xKey} tick={TICK} width={90} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} tick={TICK} />
            <YAxis tick={TICK} tickFormatter={fmt} />
          </>
        )}
        <Tooltip {...TOOLTIP_STYLE} formatter={fmt ? v => [fmt(v)] : undefined} />
        {bars.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e' }} />}
        {bars.map((bar, idx) => (
          <Bar
            key={bar.key}
            dataKey={bar.key}
            name={bar.label || bar.key}
            fill={colors[idx % colors.length]}
            stackId={stacked ? 'stack' : undefined}
            radius={!stacked || idx === bars.length - 1 ? [3, 3, 0, 0] : undefined}
          >
            {showLabels && (
              <LabelList
                dataKey={bar.key}
                position={horizontal ? 'right' : 'top'}
                formatter={fmt}
                style={{ fill: '#e6edf3', fontWeight: 700, fontSize: 10 }}
              />
            )}
          </Bar>
        ))}
      </RC>
    </ResponsiveContainer>
  );
}
