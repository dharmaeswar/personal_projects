# Analytics Warehouse Modelling — Dimensional Model for Service Usage Data

## Problem statement

Usage data for cloud-style services arrives as raw JSON feeds (service
usage events, account metadata, region metadata). Analysts need trusted,
history-preserving answers — "which services drive cost, in which
regions, for which accounts, and how is adoption trending?" — but raw
events cannot answer that directly: service tiers and pricing change
over time, bad rows slip in, and re-running a load must not double-count.

This project builds a **dimensional-model analytics warehouse** (a star
schema) from those feeds, with data contracts, SCD Type 2 history,
incremental loads, data-quality checks, SLA-tracked freshness, and
reporting SQL — all runnable locally.

## Design — star schema

```
dim_date ──────────┐
dim_service (SCD2) ┼──► fact_service_usage (daily grain, one row per event)
dim_account ───────┤         event_id UNIQUE · usage_qty / cost_usd ≥ 0
dim_region ────────┘
load_state (watermark: last batch, max usage date)
```

- **fact_service_usage** — grain: one service's usage by one account in
  one region on one day, for one source event. Foreign keys to all four
  dimensions; `CHECK (usage_qty >= 0)` / `CHECK (cost_usd >= 0)`.
- **dim_service — SCD Type 2** on tier / pricing model. A change closes
  the current row (`effective_to` = day before the change,
  `is_current = 0`) and opens a new row, so a fact always points at the
  service version in force on its usage date (point-in-time lookup).
- **dim_account / dim_region — SCD Type 1** (current value only; upsert).
- **dim_date** — calendar dimension (`date_key` = YYYYMMDD, quarter,
  weekday, weekend flag), built from usage dates as they arrive.
- **load_state** — watermark table recording the last batch id and the
  newest usage date loaded.

## Pipeline

1. **Contracts** (`src/contracts.py`) — a JSON-schema-like contract per
   feed (required fields, types, allowed tiers / pricing models / units,
   `YYYY-MM-DD` dates, non-negative numbers). Violations are rejected.
2. **Quarantine** — rejected rows are kept with their reasons
   (in the run report), never silently dropped; events naming an unknown
   account/region are quarantined too (referential gap).
3. **Incremental load** (`src/loader.py`) — only `event_id`s not already
   in the fact are inserted, so re-running a batch inserts 0 rows
   (idempotent). Reference feeds are upserted.
4. **Quality checks** (`src/quality.py`) — referential integrity
   fact→dims, no null/negative usage, no duplicate events, SCD2 single
   current version with no overlapping ranges, and a freshness/SLA check
   (data must be loaded within **2 days** of the usage date).
5. **Analytics** (`src/analytics.py`) — 4 reporting queries over the
   star schema only: service adoption trend (monthly), revenue driver by
   service/region (with % of total cost), cost per account, daily cost
   trend.
6. **Run report** (`src/run.py`) — prints and saves
   `output/run_report.json` (rows loaded, quarantined, SLA status,
   per-check pass/fail) and `output/analytics.json`.
7. **MCP tool server** (`src/mcp_server.py`, added Nov 28, 2026) — a
   stdio JSON-RPC 2.0 server exposing the warehouse to AI-native clients
   (Claude Code, Codex, or any MCP client) as five named tools:
   `warehouse_health`, `service_adoption_trend`,
   `revenue_driver_by_service_region`, `cost_per_account`,
   `daily_cost_trend`. It opens the warehouse read-only and only runs the
   fixed reporting queries, so a tool call can never write to the
   warehouse or run arbitrary SQL. This is the self-serve layer: an
   analyst or an AI assistant asks for a metric by name and gets the same
   modelled, quality-checked numbers the reports use.

## How to run

```bash
# from this project folder
python -m pytest -q            # run the test suite
python -m src.run --run-date 2026-11-13
python -m src.run --run-date 2026-11-13   # re-run: inserts 0 new facts (idempotent)
# MCP tool server (needs a warehouse first — run src.run above)
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo","version":"0.1"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"warehouse_health","arguments":{"run_date":"2026-11-13"}}}' \
  | python -m src.mcp_server --db output/warehouse.db
```

Sample data lives in `data/` (24 valid usage events across Oct–Nov 2026,
including a STORAGE tier change from `standard` to `premium` that
exercises SCD2, plus 3 bad rows that are quarantined: a negative cost,
a missing `cost_usd`, and an unknown account).

## What the checks prove (sample run, `--run-date 2026-11-13`)

- 24 facts loaded, 0 skipped on first run; 3 rows quarantined with reasons.
- Re-run inserts 0 new facts (idempotency).
- STORAGE has 2 SCD2 versions: `standard` closed 2026-11-02,
  `premium` current from 2026-11-03; facts keep the version in force
  on their usage date.
- All quality checks pass; SLA passes (newest usage date 2026-11-12,
  lag 1 day ≤ 2-day SLA). A run dated 2026-11-15+ would flag SLA FAIL.

## Honest limits

- **Local SQLite demo, not AWS production.** It uses `sqlite3` and the
  Python standard library + pytest only. It does **not** use Spark,
  Redshift, Glue, EMR, Kinesis, or any AWS service, and no claim is
  made that it ran in production.
- The MCP server is a hand-rolled stdio JSON-RPC 2.0 implementation
  (stdlib only), not the MCP Python SDK, and it exposes only the five
  fixed reporting queries — no arbitrary SQL, no writes, no resources
  or prompts surface.
- Sample data is synthetic and illustrative, not real AWS billing data.
- SCD2 applies to service tier/pricing only; accounts and regions are
  Type 1. Late-arriving events (usage date before an already-loaded
  newer tier change) resolve to the version in force on that date, but
  out-of-order tier changes are not re-stated historically.
- The SLA check measures warehouse freshness (run date vs newest usage
  date), not an upstream pipeline's delivery time.

## Layout

```
src/
  contracts.py   data contracts + validator
  model.py       star-schema DDL (SQLite)
  loader.py      reference upserts, SCD2, incremental fact load
  quality.py     data-quality + freshness/SLA checks
  analytics.py   reporting SQL
  run.py         end-to-end run + JSON report
  mcp_server.py  MCP tool server (stdio JSON-RPC): 5 tools over the warehouse
tests/           pytest suite (contracts, SCD2, idempotency, checks, analytics, MCP server)
data/            sample JSON feeds
output/          warehouse.db, run_report.json, analytics.json (generated)
```
