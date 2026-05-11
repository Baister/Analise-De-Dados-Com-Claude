import { describe, it, expect } from 'vitest';
import { sortRows } from './sort';

const ROWS = [
  { nome: 'Carlos', valor: 300 },
  { nome: 'Ana',    valor: 100 },
  { nome: 'Marcos', valor: 200 },
];

describe('sortRows', () => {
  it('retorna igual sem coluna', () => {
    expect(sortRows(ROWS, null, 'asc')).toEqual(ROWS);
  });
  it('ordena numérico asc', () => {
    const r = sortRows(ROWS, 'valor', 'asc');
    expect(r.map(x => x.valor)).toEqual([100, 200, 300]);
  });
  it('ordena numérico desc', () => {
    const r = sortRows(ROWS, 'valor', 'desc');
    expect(r.map(x => x.valor)).toEqual([300, 200, 100]);
  });
  it('ordena string asc', () => {
    const r = sortRows(ROWS, 'nome', 'asc');
    expect(r[0].nome).toBe('Ana');
  });
  it('não muta o array original', () => {
    const orig = [...ROWS];
    sortRows(ROWS, 'valor', 'desc');
    expect(ROWS).toEqual(orig);
  });
});
