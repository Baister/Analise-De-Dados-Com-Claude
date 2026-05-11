import {
  AreaChart as RC, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from 'recharts';

const TOOLTIP_STYLE = {
  contentStyle: { background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 },
  labelStyle:   { color: '#e6edf3' },
  itemStyle:    { color: '#8b949e' },
};
const TICK   = { fill: '#8b949e', fontSize: 10 };
const GRID   = { strokeDasharray: '3 3', stroke: '#30363d' };
const COLORS = ['#238636', '#da3633', '#1f6feb', '#d29922'];

// areas: [{ key, label?, formatter? }]
export default function AreaChart({ data, xKey, areas = [], colors = COLORS, height = 220 }) {
  if (!data?.length || !areas.length) {
    return (
      <div className="flex items-center justify-center h-[220px] text-subtext text-sm">
        Sem dados
      </div>
    );
  }
  const fmt = areas[0]?.formatter;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RC data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <defs>
          {areas.map((a, idx) => (
            <linearGradient key={a.key} id={`grad_${a.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"    stopColor={colors[idx % colors.length]} stopOpacity={0.35} />
              <stop offset="100%" stopColor={colors[idx % colors.length]} stopOpacity={0}    />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} tick={TICK} />
        <YAxis tick={TICK} tickFormatter={fmt} />
        <Tooltip {...TOOLTIP_STYLE} formatter={fmt ? v => [fmt(v)] : undefined} />
        {areas.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e' }} />}
        {areas.map((area, idx) => (
          <Area
            key={area.key}
            type="monotone"
            dataKey={area.key}
            name={area.label || area.key}
            stroke={colors[idx % colors.length]}
            fill={`url(#grad_${area.key})`}
            strokeWidth={2}
          />
        ))}
      </RC>
    </ResponsiveContainer>
  );
}
