import { describe, it, expect } from 'vitest';
import { getEaster, getHolidaysSP, countBusinessDaysSP } from './businessDays';

describe('getEaster', () => {
  it('calcula Páscoa 2025 (20 de abril)', () => {
    const e = getEaster(2025);
    expect(e.getFullYear()).toBe(2025);
    expect(e.getMonth()).toBe(3); // April = index 3
    expect(e.getDate()).toBe(20);
  });
  it('calcula Páscoa 2026 (5 de abril)', () => {
    const e = getEaster(2026);
    expect(e.getFullYear()).toBe(2026);
    expect(e.getMonth()).toBe(3);
    expect(e.getDate()).toBe(5);
  });
});

describe('getHolidaysSP', () => {
  it('contém Natal (25/12)', () => {
    expect(getHolidaysSP(2026).has('2026-12-25')).toBe(true);
  });
  it('contém Fundação de SP (25/01)', () => {
    expect(getHolidaysSP(2026).has('2026-01-25')).toBe(true);
  });
  it('contém Dia da Consciência Negra (20/11)', () => {
    expect(getHolidaysSP(2026).has('2026-11-20')).toBe(true);
  });
  it('contém Carnaval segunda 2026 (16/02 — Páscoa 5/abr − 48d)', () => {
    expect(getHolidaysSP(2026).has('2026-02-16')).toBe(true);
  });
  it('contém Carnaval terça 2026 (17/02 — Páscoa 5/abr − 47d)', () => {
    expect(getHolidaysSP(2026).has('2026-02-17')).toBe(true);
  });
  it('contém Sexta-feira Santa 2026 (03/04 — Páscoa 5/abr − 2d)', () => {
    expect(getHolidaysSP(2026).has('2026-04-03')).toBe(true);
  });
  it('contém Corpus Christi 2026 (04/06 — Páscoa 5/abr + 60d)', () => {
    expect(getHolidaysSP(2026).has('2026-06-04')).toBe(true);
  });
});

describe('countBusinessDaysSP', () => {
  it('fevereiro 2026 tem 18 dias úteis (20 Seg–Sex − 2 dias de Carnaval)', () => {
    expect(countBusinessDaysSP(2026, 2)).toBe(18);
  });
  it('maio 2026 tem 20 dias úteis (21 Seg–Sex − 1 feriado 01/05)', () => {
    expect(countBusinessDaysSP(2026, 5)).toBe(20);
  });
  it('retorna sempre pelo menos 1', () => {
    expect(countBusinessDaysSP(2026, 1)).toBeGreaterThanOrEqual(1);
  });
});
