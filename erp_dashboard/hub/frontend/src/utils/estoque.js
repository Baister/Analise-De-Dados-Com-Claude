// hub/frontend/src/utils/estoque.js

/**
 * Classifica itens em Curva A/B/C pelo val_vendido_90d acumulado.
 * A = top 80% do faturamento | B = 80–95% | C = abaixo de 95%
 * Retorna novo array com campo `abc` adicionado, ordenado por val desc.
 */
export function classifyABC(items) {
  const total = items.reduce((s, r) => s + (r.val_vendido_90d ?? 0), 0);
  if (total === 0) return items.map(r => ({ ...r, abc: 'C' }));
  const sorted = [...items].sort((a, b) => (b.val_vendido_90d ?? 0) - (a.val_vendido_90d ?? 0));
  let acc = 0;
  return sorted.map(r => {
    acc += (r.val_vendido_90d ?? 0) / total;
    return { ...r, abc: acc <= 0.8 ? 'A' : acc <= 0.95 ? 'B' : 'C' };
  });
}
