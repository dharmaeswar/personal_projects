# Trade Surveillance Lakehouse

The global data layer a compliance-technology team needs: a medallion
lakehouse (bronze → silver → gold) for order, execution and market
data, built the way a Data Engineer on a trade-surveillance team would
build it — dimensional modelling, partitioned Parquet, Iceberg-style
snapshots, data-quality checks at every layer, a CAT-ready report
export, and measured query tuning.

Built for the Susquehanna (SIG) — Data Engineer, Compliance Technology
(Experienced Hire, Job 12047, Bala Cynwyd, Nov 2026) application: the
team's biggest effort is a global data layer for middle/back office,
plus proprietary surveillance models and the data foundations behind
them. The JD asks for data modelling, a lakehouse / columnar stack
(Parquet, Iceberg, Trino), large time-series event data, Python
prototyping, and surveillance / regulatory-reporting support including
CAT.

**All data is synthetic and seeded (seed 42).** No real market data,
orders, accounts, or CAT submissions are involved, and nothing here
claims to be a production system.

## What it does

1. **Generate** (`surveillance_lakehouse/generate.py`) — seeded order,
   execution and market-trade events for 6 instruments, 10 accounts,
   5 business days: 2,040 orders, ~1,400 executions, 1,500 market
   trades. Deliberate defects are planted: 5 duplicate orders, 3
   missing accounts, 2 non-positive quantities, 2 trade-date
   mismatches, 2 late-arriving executions — plus a wash-trade pattern
   (ACC-007 buys and sells AAPL in matched size every day).
2. **Bronze** (`ingest.py`) — schema-enforced raw ingest into
   Parquet datasets partitioned by `trade_date` (hive style).
   Bad rows are quarantined with a reason, never silently dropped.
3. **Silver** (`model.py`) — cleaned, deduplicated dimensional model:
   `dim_instrument`, `dim_account`, `fact_order`, `fact_execution`,
   `fact_trade`, with surrogate keys, stated grains, and referential
   integrity checks (every fact key resolves; every execution
   references a known order).
4. **Gold** (`gold.py`) — surveillance foundations:
   `account_day_features` (per account/day/symbol aggregates, cancel
   rate, wash-trade candidate flag) and `cat_events` (CAT-ready order
   events), plus a data-quality report with completeness, uniqueness
   and silver→gold notional reconciliation.
5. **CAT export** (`cat.py`) — pipe-delimited CAT-style order-event
   file (`out/cat_report.txt`): one row per firm order event. A format
   demo on synthetic data, not a real filing.
6. **Snapshots** (`snapshots.py`) — Iceberg-style versioned snapshot
   log (`_snapshots.json`) per table: snapshot id, parent, operation,
   rows added/removed.
7. **Tuning** (`tuning.py`) — partitioned scan vs full scan of
   `fact_trade`, timed with pyarrow, with file-layout guidance for a
   Trino/Iceberg deployment (partition by trade_date, ~128 MB files,
   sort by symbol, Z-order on account/symbol).

## Run it

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_pipeline.py   # builds out/ : bronze, silver, gold, CAT, tuning
.venv/bin/python -m pytest -q      # tests
```

## Demo results (seed 42, Nov 28, 2026)

- Bronze: 2,052 orders in (2,040 clean + 12 planted defects), 2,045
  written, 7 quarantined (3 missing account, 2 bad quantity,
  2 date mismatch); executions 1,313 written; trades 1,500 written.
- Silver: 2,040 fact orders (5 duplicates removed by latest-ingest
  dedupe), 1,311 fact executions (2 duplicates removed, 2 late
  arrivals counted), 1,500 fact trades; 0 referential-integrity
  violations; 0 orphan executions.
- Gold: 6 wash-trade candidates — ACC-007 on all 5 days (AAPL, 2,000
  bought = 2,000 sold each day, the planted pattern) plus ACC-003 on
  one day, a random coincidence in the seeded data that a reviewer
  would clear; silver→gold notional reconciliation matches exactly
  ($323,957,056.80 both sides, difference 0.0).
- CAT: 2,040 pipe-delimited rows (1,878 MEOA order-accepted,
  162 MEOC cancelled), no nulls.
- Tuning: partitioned scan 1.58 ms vs full scan 1.98 ms (1.25x) for
  AAPL trades on 2026-11-18 — small in absolute terms at 1,500 rows,
  and the report says so.

## Honest limits (stated so the resume never over-claims)

- Data is synthetic and seeded; the demo is ~5,000 rows, not the
  billions of records the real system holds. The patterns (partition
  pruning, predicate pushdown, dedupe, quarantine, reconciliation)
  are the same at that scale; the volume is not proven here.
- Parquet is real (pyarrow); Iceberg and Trino are the stated
  production targets, not runtimes used here — the snapshot log is
  Iceberg-style JSON bookkeeping, and the tuning scan is pyarrow,
  not a Trino cluster.
- The CAT file is a format demo on synthetic data, never filed.
- The wash-trade flag is a screening candidate (matched buy/sell
  size), not a finding of abuse — it queues work for a human
  reviewer.
