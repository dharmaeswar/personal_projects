# Post-Trade Reconciliation Service

A Python post-trade service in the shape of Akuna Capital's Post Trade
team (Middle Office, Compliance, Risk, Trade Enrichment): it enriches
executions with instrument reference data, reconciles them intraday
against clearing records, builds positions, and calculates P&L —
persisted in PostgreSQL.

## What it does

1. **Enrich** (`posttrade/enrichment.py`) — joins each execution to
   reference data (underlying, option type, expiry, strike, contract
   multiplier, currency, exchange, tick size) and computes notional.
   Unknown symbols are flagged, never dropped silently.
2. **Reconcile** (`posttrade/reconciliation.py`) — matches executions
   to clearing records on symbol, side, trade date and account, then
   quantity, then price within tolerance (max $0.05, two ticks).
   Anything else becomes a break: `MISSING_CLEARING`,
   `MISSING_EXECUTION`, `QTY_MISMATCH`, `PRICE_BREAK`.
3. **Positions** (`posttrade/positions.py`) — net quantity and average
   cost per account / symbol, from reconciled trades only, so breaks
   never leak into the book.
4. **P&L** (`posttrade/pnl.py`) — realised P&L on position reductions
   and unrealised P&L against mark prices, average-cost method.
5. **Store** (`posttrade/store.py`, `schema.sql`) — the production
   store is PostgreSQL (DDL in `schema.sql`); local runs and tests use
   SQLite from the standard library as a stand-in with the same tables.

## Run

```bash
pip install -r requirements.txt
python -m pytest -q
python run_posttrade.py
```

Demo output: 8 executions, 7 clearing records, 5 matched, 4 breaks
(2 missing clearing, 1 missing execution, 1 quantity mismatch),
realised P&L $120.00, unrealised P&L $590.00, total $710.00.
The run writes `posttrade_report.json`.

## Layout

- `posttrade/models.py` — executions, clearing records, instruments, matches, breaks, positions, P&L
- `posttrade/enrichment.py` — reference data + enrichment
- `posttrade/reconciliation.py` — intraday matching engine and breaks
- `posttrade/positions.py` — average-cost positions
- `posttrade/pnl.py` — realised / unrealised P&L
- `posttrade/store.py` — SQLite stand-in store (PostgreSQL DDL in `schema.sql`)
- `posttrade/service.py` — orchestration: enrich → reconcile → positions → P&L → store
- `run_posttrade.py` — seeded demo runner
- `tests/` — pytest suites for enrichment, reconciliation, positions/P&L, store and service

## Honest limits

All trade, clearing and reference data is synthetic and seeded. No
live trading, clearing or market-data connection is claimed, and the
SQLite store is a local stand-in for the PostgreSQL schema in
`schema.sql`. No Akuna Capital affiliation is claimed.
