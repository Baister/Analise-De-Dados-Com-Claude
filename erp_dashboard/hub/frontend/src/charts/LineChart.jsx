import {
  LineChart as RC, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from 'recharts';

const TOOLTIP_STYLE = {
  contentStyle: { background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 },
  labelStyle:   { color: '#e6edf3' },
  itemStyle:    { color: '#8b949e' },
};
const TICK   = { fill: '#8b949e', fontSize: 10 };
const GRID   = { strokeDasharray: '3 3', stroke: '#30363d' };
const COLORS = ['#1f6feb', '#238636', '#d29922', '#da3633'];

// lines: [{ key, label?, formatter? }]
export default function LineChart({ data, xKey, lines = [], colors = COLORS, height = 220 }) {
  if (!data?.length || !lines.length) {
    return (
      <div className="flex items-center justify-center h-[220px] text-subtext text-sm">
        Sem dados
      </div>
    );
  }
  const fmt = lines[0]?.formatter;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RC data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} tick={TICK} />
        <YAxis tick={TICK} tickFormatter={fmt} />
        <Tooltip {...TOOLTIP_STYLE} formatter={fmt ? v => [fmt(v)] : undefined} />
        {lines.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e' }} />}
        {lines.map((line, idx) => (
          <Line
            key={line.key}
            type="monotone"
            dataKey={line.key}
            name={line.label || line.key}
            stroke={colors[idx % colors.length]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        ))}
      </RC>
    </ResponsiveContainer>
  );
}
