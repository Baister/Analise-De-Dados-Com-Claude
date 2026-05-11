// FilterBar — ponto de extensão para novos tipos de filtro.
// filters: [{ key, label, type: 'select'|'daterange'|'text', options? }]
// values: { [key]: value }
// onChange: (newValues) => void

export default function FilterBar({ filters, values, onChange }) {
  if (!filters?.length) return null;
  return (
    <div className="bg-sidebar border border-card_border rounded-lg px-4 py-3 flex gap-4 flex-wrap items-end mb-4">
      {filters.map(f => (
        <div key={f.key} className="flex flex-col gap-1">
          <label className="text-subtext text-[10px] uppercase tracking-wider">
            {f.label}
          </label>

          {f.type === 'select' && (
            <select
              value={values[f.key] || 'todos'}
              onChange={e => onChange({ ...values, [f.key]: e.target.value })}
              className="bg-bg border border-card_border rounded px-2 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent min-w-[130px]"
            >
              {(f.options || ['todos']).map(opt => (
                <option key={opt} value={opt}>
                  {opt === 'todos' ? 'Todos' : opt}
                </option>
              ))}
            </select>
          )}

          {f.type === 'daterange' && (
            <div className="flex gap-1 items-center">
              <input
                type="date"
                value={values[`${f.key}_de`] || ''}
                onChange={e => onChange({ ...values, [`${f.key}_de`]: e.target.value })}
                className="bg-bg border border-card_border rounded px-2 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent"
              />
              <span className="text-subtext text-xs">→</span>
              <input
                type="date"
                value={values[`${f.key}_ate`] || ''}
                onChange={e => onChange({ ...values, [`${f.key}_ate`]: e.target.value })}
                className="bg-bg border border-card_border rounded px-2 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent"
              />
            </div>
          )}

          {f.type === 'text' && (
            <input
              type="text"
              value={values[f.key] || ''}
              onChange={e => onChange({ ...values, [f.key]: e.target.value })}
              placeholder={f.placeholder || `Buscar ${f.label}…`}
              className="bg-bg border border-card_border rounded px-2 py-1.5 text-text_main text-xs focus:outline-none focus:border-accent min-w-[130px]"
            />
          )}
        </div>
      ))}
    </div>
  );
}
