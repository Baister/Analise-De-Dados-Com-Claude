import { describe, it, expect } from 'vitest';
import { applyFilters, getUniqueValues } from './filters';

const ROWS = [
  { vendedor: 'Carlos', marca: 'Marca A', faturamento: 100 },
  { vendedor: 'Ana',    marca: 'Marca B', faturamento: 200 },
  { vendedor: 'Carlos', marca: 'Marca B', faturamento: 300 },
];

describe('applyFilters', () => {
  it('retorna todos sem filtros', () => {
    expect(applyFilters(ROWS, {})).toHaveLength(3);
  });
  it('filtra por vendedor', () => {
    const r = applyFilters(ROWS, { vendedor: 'Carlos' });
    expect(r).toHaveLength(2);
    expect(r.every(row => row.vendedor === 'Carlos')).toBe(true);
  });
  it('filtra por múltiplos campos (AND)', () => {
    const r = applyFilters(ROWS, { vendedor: 'Carlos', marca: 'Marca B' });
    expect(r).toHaveLength(1);
    expect(r[0].faturamento).toBe(300);
  });
  it('ignora filtro "todos"', () => {
    expect(applyFilters(ROWS, { vendedor: 'todos' })).toHaveLength(3);
  });
  it('ignora filtro vazio', () => {
    expect(applyFilters(ROWS, { vendedor: '' })).toHaveLength(3);
  });
});

describe('getUniqueValues', () => {
  it('retorna "todos" + valores únicos ordenados', () => {
    expect(getUniqueValues(ROWS, 'vendedor')).toEqual(['todos', 'Ana', 'Carlos']);
  });
});
