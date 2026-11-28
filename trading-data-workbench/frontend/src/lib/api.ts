/** Typed client for the trading data workbench API. */

export interface Instrument {
  symbol: string;
  name: string;
  asset_class: string;
  currency: string;
  exchange: string;
  base_price: number;
  latest_quote?: Quote;
}

export interface Quote {
  symbol: string;
  ts: string;
  bid: number;
  ask: number;
  last: number;
  volume: number;
}

export interface Order {
  id: number;
  symbol: string;
  side: "BUY" | "SELL";
  qty: number;
  order_type: "MARKET" | "LIMIT";
  limit_price: number | null;
  status: "filled" | "open";
  filled_qty: number;
  filled_price: number | null;
  idempotency_key: string | null;
  created_at: string;
}

export interface NewOrder {
  symbol: string;
  side: "BUY" | "SELL";
  qty: number;
  order_type: "MARKET" | "LIMIT";
  limit_price?: number;
}

export interface Position {
  symbol: string;
  qty: number;
  avg_cost: number;
  last_price: number;
  market_value: number;
  unrealized_pnl: number;
}

export interface QualityEntry {
  symbol: string;
  rows_checked: number;
  issues: string[];
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class TradingApi {
  private readonly baseUrl: string;

  constructor(baseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, init);
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new ApiError(resp.status, (body as { error?: string }).error ?? resp.statusText);
    }
    return body as T;
  }

  listInstruments(): Promise<{ instruments: Instrument[] }> {
    return this.request("/api/instruments");
  }

  getQuotes(symbol: string, limit = 60): Promise<{ symbol: string; quotes: Quote[] }> {
    return this.request(`/api/quotes?symbol=${encodeURIComponent(symbol)}&limit=${limit}`);
  }

  placeOrder(order: NewOrder, idempotencyKey?: string): Promise<Order> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    return this.request("/api/orders", {
      method: "POST",
      headers,
      body: JSON.stringify(order),
    });
  }

  listPositions(): Promise<{ positions: Position[] }> {
    return this.request("/api/positions");
  }

  getDataQuality(): Promise<{ report: QualityEntry[] }> {
    return this.request("/api/data-quality");
  }
}

export const api = new TradingApi();
