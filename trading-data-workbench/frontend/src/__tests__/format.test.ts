import { describe, expect, it } from "vitest";
import { formatMoney, formatPct, formatSignedMoney, pnlClass, spreadBps } from "../lib/format";

describe("format helpers", () => {
  it("formats money with two decimals", () => {
    expect(formatMoney(232.5)).toBe("$232.50");
    expect(formatMoney(1000)).toBe("$1,000.00");
  });

  it("signs gains and losses", () => {
    expect(formatSignedMoney(12.345)).toBe("+$12.35");
    expect(formatSignedMoney(-3)).toBe("-$3.00");
    expect(formatSignedMoney(0)).toBe("$0.00");
  });

  it("formats percents", () => {
    expect(formatPct(0.0123)).toBe("1.23%");
  });

  it("computes spread in basis points", () => {
    expect(spreadBps(100, 100.1)).toBeCloseTo(9.995, 2);
    expect(spreadBps(0, 0)).toBe(0);
  });

  it("classifies P&L", () => {
    expect(pnlClass(1)).toBe("gain");
    expect(pnlClass(-1)).toBe("loss");
    expect(pnlClass(0)).toBe("flat");
  });
});
