# Trading Data Workbench

A financial trading application in miniature: a Python API serving synthetic
equity, ETF, and fixed-income market data, plus a Vue 3 + TypeScript
dashboard that trades against it. Built for the FactSet — Senior Software
Engineer (Python, TypeScript, Vue 3 or Go) application (Req R33494).

**All data is synthetic and seeded deterministically.** No real market data,
prices, or positions are used, and nothing here is a claim about any real
institution.

## What it does

- **Instruments** — 8 synthetic instruments (AAPL, MSFT, NVDA, JPM, XOM, SPY,
  GLD, TLT) across equities, ETFs, and fixed income, with exchange and
  currency.
- **Quotes** — 60 hourly bid/ask/last bars per instrument, seeded by a
  deterministic random walk. `GET /api/quotes?symbol=AAPL&limit=60`.
- **Orders** — market and limit orders with full validation. Market orders
  fill at the latest mid; limit orders fill only when the limit crosses the
  mid, otherwise they stay open. Sells are rejected when the position does
  not cover them (HTTP 422). `POST /api/orders` accepts an `Idempotency-Key`
  header: replaying a key returns the original order instead of a duplicate.
- **Positions** — computed from filled orders: quantity, average cost,
  market value at the latest quote, and unrealised P&L.
- **Data quality** — the same checks a validation reviewer runs on a feed:
  positive prices, bid ≤ last ≤ ask, spread within 200 bps, no future
  timestamps, no duplicate timestamps, no gaps over 2 hours, ordered series.
  `GET /api/data-quality` reports 480 seeded rows with zero issues.
- **Observability** — `GET /health` and `GET /metrics` (Prometheus-format
  request counts and uptime).
- **Dashboard** — Vue 3 + TypeScript (Vite): instrument table, latest-quote
  panel with spread in basis points, order form with client-side validation,
  positions table with P&L, and the data-quality report.

## Stack

- Backend: Python 3.11+ standard library only (no third-party runtime deps).
  `ThreadingHTTPServer` with a store lock serialising order writes, so
  concurrent requests cannot oversell a position.
- Storage: SQLite in-memory for the demo. `schema.sql` is written in
  standard SQL and runs unchanged on PostgreSQL, the intended production
  store; the same DDL is the Postgres target.
- Frontend: Vue 3.5 + TypeScript + Vite, with a typed API client
  (`src/lib/api.ts`) and Vitest tests.

## Run it

```bash
# Backend (listens on http://127.0.0.1:8000)
python run_service.py

# Frontend (proxies /api to the backend)
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

## Tests — all passing

Backend: 16 pytest tests (`backend/tests/test_app.py`) — instruments, quote
ordering and validation, order validation errors, idempotent replay, sell
coverage, limit-order crossing, position math, data-quality report, metrics,
unknown routes. Run with:

```bash
PYTHONPATH=$HOME/.local/lib/python3.12/site-packages python -m pytest backend/tests -q
```

Frontend: 13 Vitest tests (`frontend/src/__tests__/`) — typed API client
(including the idempotency header), money/spread formatting, and the order
form (validation errors, limit-price rules, emitted payload). Run with:

```bash
cd frontend && npm test
```

The production build also passes: `cd frontend && npm run build`.

## Honest limits

- Data is synthetic and seeded; this is not a live market feed and not a
  production trading system.
- The demo store is SQLite in-memory; the Postgres DDL is provided but the
  service has not been run against a real Postgres instance.
- The dashboard is demo-scale (single page, no auth, no real-time streaming).
- No Go code is included: Go is listed as an alternative in the job posting,
  and this project covers the Python + TypeScript + Vue 3 path instead.
- AI/ML integration is not part of this project; the author's LLM and
  evaluation work lives in other projects in this repo.
