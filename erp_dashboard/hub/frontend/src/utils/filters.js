// filters.js — ponto central de extensão para novos tipos de filtro.
// Para novo tipo: adicionar um case em applyFilters().

export function applyFilters(rows, activeFilters) {
  return rows.filter(row =>
    Object.entries(activeFilters).every(([key, value]) => {
      if (!value || value === 'todos') return true;
      const cell = String(row[key] ?? '').toLowerCase();
      return cell.includes(String(value).toLowerCase());
    })
  );
}

export function applyDateFilter(rows, dateKey, de, ate) {
  return rows.filter(row => {
    const d = new Date(row[dateKey]);
    if (isNaN(d)) return true;
    if (de  && d < new Date(de))  return false;
    if (ate && d > new Date(ate)) return false;
    return true;
  });
}

export function getUniqueValues(rows, key) {
  const vals = [...new Set(rows.map(r => r[key]).filter(Boolean))].sort();
  return ['todos', ...vals];
}

export function agregaPorDia(rows, filterKey = null, filterValue = null) {
  const src = filterKey && filterValue
    ? rows.filter(r => r[filterKey] === filterValue)
    : rows;
  const map = {};
  for (const r of src) {
    if (!map[r.dia]) map[r.dia] = { dia: r.dia, faturamento: 0 };
    map[r.dia].faturamento += r.faturamento ?? 0;
  }
  return Object.values(map).sort((a, b) => (a.dia < b.dia ? -1 : 1));
}
