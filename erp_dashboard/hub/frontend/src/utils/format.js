export function brl(value) {
  if (value == null) return 'R$ —';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
  }).format(value);
}

export function pct(value, decimals = 1) {
  if (value == null) return '—%';
  return `${Number(value).toFixed(decimals).replace('.', ',')}%`;
}

export function fmtDate(isoStr) {
  if (!isoStr) return '—';
  // Parse date-only strings as local time (not UTC) to avoid timezone day shift
  const match = String(isoStr).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) {
    const d = new Date(+match[1], +match[2] - 1, +match[3]);
    return d.toLocaleDateString('pt-BR');
  }
  return new Date(isoStr).toLocaleDateString('pt-BR');
}

export function shortBrl(value) {
  if (value == null || Number.isNaN(value)) return '—';
  if (value >= 1_000_000) return `R$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000)     return `R$${(value / 1_000).toFixed(0)}k`;
  return brl(value);
}
