import { describe, expect, it, vi } from "vitest";
import { ApiError, TradingApi } from "../lib/api";

function mockFetch(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
      statusText: "Error",
    }),
  );
}

describe("TradingApi", () => {
  it("lists instruments from /api/instruments", async () => {
    mockFetch({ instruments: [{ symbol: "AAPL", name: "Apple Inc." }] });
    const api = new TradingApi("http://test");
    const result = await api.listInstruments();
    expect(result.instruments[0].symbol).toBe("AAPL");
    expect(fetch).toHaveBeenCalledWith(
      "http://test/api/instruments",
      undefined,
    );
  });

  it("throws ApiError with the server message on failure", async () => {
    mockFetch({ error: "unknown symbol: NOPE" }, 404);
    const api = new TradingApi("http://test");
    await expect(api.getQuotes("NOPE")).rejects.toThrow(ApiError);
    await expect(api.getQuotes("NOPE")).rejects.toThrow("unknown symbol: NOPE");
  });

  it("sends the idempotency key when placing an order", async () => {
    mockFetch({ id: 1, status: "filled" }, 201);
    const api = new TradingApi("http://test");
    const order = await api.placeOrder(
      { symbol: "AAPL", side: "BUY", qty: 5, order_type: "MARKET" },
      "key-123",
    );
    expect(order.id).toBe(1);
    expect(fetch).toHaveBeenCalledWith(
      "http://test/api/orders",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "Idempotency-Key": "key-123" }),
      }),
    );
  });

  it("encodes the symbol and limit in the quotes query", async () => {
    mockFetch({ symbol: "MSFT", quotes: [] });
    const api = new TradingApi("http://test");
    await api.getQuotes("MSFT", 5);
    expect(fetch).toHaveBeenCalledWith("http://test/api/quotes?symbol=MSFT&limit=5", undefined);
  });
});
