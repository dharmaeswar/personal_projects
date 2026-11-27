import { describe, expect, it } from 'vitest';
import {
  buildSchedule,
  minimumDue,
  monthlyPayment,
  splitPayment,
} from './amortization';

describe('amortization math', () => {
  it('matches the known payment for $300,000 at 6.5% over 360 months', () => {
    // Same value the backend test pins: $1,896.20.
    expect(monthlyPayment(300000, 6.5, 360)).toBe(1896.2);
  });

  it('matches the known payment for $250,000 at 7.0% over 360 months', () => {
    expect(monthlyPayment(250000, 7.0, 360)).toBe(1663.26);
  });

  it('divides principal evenly at a 0% rate', () => {
    expect(monthlyPayment(10000, 0, 12)).toBe(833.33);
  });

  it('splits the first month into $1,625.00 interest and $271.20 principal', () => {
    const split = splitPayment(2146.2, 300000, 6.5, 250);
    expect(split).toEqual({ interest: 1625, principal: 271.2, escrow: 250 });
  });

  it('sets the minimum due to interest plus escrow', () => {
    expect(minimumDue(300000, 6.5, 250)).toBe(1875);
  });

  it('builds a 360-row schedule that repays the full balance', () => {
    const rows = buildSchedule(300000, 6.5, 1896.2, 0, 360);
    expect(rows).toHaveLength(360);
    expect(rows[0]).toMatchObject({ month: 1, interest: 1625, principal: 271.2 });
    expect(rows[359].remainingBalance).toBe(0);
    const principalSum = rows.reduce((sum, row) => sum + row.principal, 0);
    expect(Math.round(principalSum * 100) / 100).toBe(300000);
  });

  it('shortens the schedule after payments', () => {
    const rows = buildSchedule(299728.8, 6.5, 1896.2, 250, 359, 2);
    expect(rows).toHaveLength(359);
    expect(rows[0].month).toBe(2);
  });
});
