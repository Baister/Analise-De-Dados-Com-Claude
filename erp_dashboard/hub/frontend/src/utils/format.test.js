import { describe, it, expect } from 'vitest';
import { brl, pct, fmtDate } from './format';

describe('brl', () => {
  it('retorna marcador para null', () => { expect(brl(null)).toBe('R$ —'); });
  it('formata inteiro', () => { expect(brl(1000)).toContain('1.000'); });
  it('formata decimal', () => { expect(brl(1234.56)).toContain('1.234'); });
});

describe('pct', () => {
  it('retorna marcador para null', () => { expect(pct(null)).toBe('—%'); });
  it('formata com 1 decimal', () => { expect(pct(71.234)).toBe('71,2%'); });
  it('aceita casas customizadas', () => { expect(pct(50, 0)).toBe('50%'); });
});

describe('fmtDate', () => {
  it('retorna marcador para null', () => { expect(fmtDate(null)).toBe('—'); });
  it('formata data ISO', () => {
    const result = fmtDate('2026-01-15');
    expect(result).toContain('15');
  });
});
