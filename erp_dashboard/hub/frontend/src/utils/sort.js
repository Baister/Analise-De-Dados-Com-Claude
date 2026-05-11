export function sortRows(rows, col, dir) {
  if (!col) return rows;
  return [...rows].sort((a, b) => {
    const av = a[col], bv = b[col];
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === 'number'
      ? av - bv
      : String(av).localeCompare(String(bv), 'pt-BR');
    return dir === 'asc' ? cmp : -cmp;
  });
}
