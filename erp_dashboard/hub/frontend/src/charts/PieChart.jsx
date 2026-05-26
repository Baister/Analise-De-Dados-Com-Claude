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
export default function PieChart({
  data, nameKey, valueKey, showValue = false, formatter, height = 200, highlightKey = null,
}) {
  if (!data?.length) {
    return (
      <div className="flex items-center justify-center h-[200px] text-subtext text-sm">
        Sem dados
      </div>
    );
  }
  const fmt = formatter || brl;

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
                  fill={COLORS[i % COLORS.length]}
                  fillOpacity={highlightKey ? (entry[nameKey] === highlightKey ? 1 : 0.35) : 1}
                />
              ))}
            </Pie>
            <Tooltip {...TOOLTIP} formatter={v => [fmt(v)]} />
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
              style={{ background: COLORS[i % COLORS.length] }}
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
