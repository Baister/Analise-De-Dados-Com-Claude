import { useState, useMemo } from 'react';
import { sortRows } from '../utils/sort';

// columns: [{ key, label, align?, render? }]
// render(value, row) → ReactNode para células customizadas
export default function DataTable({ columns, rows = [] }) {
  const [sort, setSort] = useState({ col: null, dir: 'asc' });

  function toggleSort(col) {
    setSort(prev =>
      prev.col === col
        ? { col, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { col, dir: 'asc' }
    );
  }

  const sorted = useMemo(() => sortRows(rows, sort.col, sort.dir), [rows, sort]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] text-subtext border-collapse">
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                onClick={() => toggleSort(col.key)}
                className="text-left px-2 py-2 text-[10px] text-text_main border-b border-card_border cursor-pointer hover:text-accent select-none whitespace-nowrap"
                style={col.align === 'right' ? { textAlign: 'right' } : {}}
              >
                {col.label}
                <span className="ml-1 opacity-40">
                  {sort.col === col.key ? (sort.dir === 'asc' ? '↑' : '↓') : '↕'}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i} className="hover:bg-progress_bg transition-colors">
              {columns.map(col => (
                <td
                  key={col.key}
                  className="px-2 py-1.5 border-b border-progress_bg"
                  style={col.align === 'right' ? { textAlign: 'right' } : {}}
                >
                  {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="text-center py-6 text-subtext">
                Sem dados
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
