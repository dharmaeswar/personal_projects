/** Money and percent formatting for the dashboard. */

export function formatMoney(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatSignedMoney(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${formatMoney(Math.abs(value))}`;
}

export function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

/** Spread in basis points between bid and ask. */
export function spreadBps(bid: number, ask: number): number {
  const mid = (bid + ask) / 2;
  if (mid <= 0) return 0;
  return ((ask - bid) / mid) * 10000;
}

export function pnlClass(value: number): "gain" | "loss" | "flat" {
  if (value > 0) return "gain";
  if (value < 0) return "loss";
  return "flat";
}
