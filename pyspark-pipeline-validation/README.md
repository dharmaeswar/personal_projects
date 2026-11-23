# PySpark Pipeline Validation

A portfolio project for a PySpark Developer role. It builds a batch data
pipeline the way a Spark job would — raw ingest, window-function dedup,
Spark-SQL-style transforms, data-quality checks with quarantine, partitioned
writes, and gold aggregates reconciled back to the cleansed layer — and
validates every stage.

**All data is synthetic and seeded (seed 42).** No real company, customer, or
order data is used, and nothing here is a claim about any real institution.

## Runs locally, without a Spark cluster

PySpark is not installed in this environment (no Spark cluster or Java
runtime here), so the pipeline runs locally with pandas + Parquet. It does
**not** pretend a cluster run happened. Every pandas operation names the Spark
operation it mirrors, so the same code maps one-to-one onto a real PySpark
job — swap the DataFrame calls for Spark equivalents and the logic is
unchanged. `requirements.txt` lists only pandas, pyarrow, numpy, pytest.

## Spark SQL mapping

| This project (pandas) | Spark equivalent |
|---|---|
| `dedupe_latest` — sort + drop duplicates | `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ingested_at DESC)` + filter `rn = 1` |
| `with_derived_columns` | `withColumn("amount_band", ...)` / `withColumn("is_high_value", ...)` |
| `filter_valid` boolean masks | `WHERE` clause / `filter()` with the same rules |
| `join_product_dim` merge | broadcast join against the 4-row product dimension |
| `aggregate_daily` groupBy | `GROUP BY event_date, region, product_category` with `sum(amount)`, `count(*)` |
| Partitioned Parquet write | `df.write.partitionBy("event_date").parquet(...)` |
| Schema enforcement | `StructType` validation before any write lands |

Tuning notes, as a Spark job would do them: the curated layer is partitioned
by `event_date` (48 partitions, one per date) so downstream reads prune to
the dates they need; the product dimension is tiny (4 rows) so it is joined
as a broadcast lookup instead of a shuffle; dedup happens before the
quality filter so bad rows are counted once, not once per duplicate copy.

## What it validates

- **Schema**: column presence, dtypes, nullability — enforced on the cleansed
  layer before it is written; raw input is checked leniently because nulls
  and bad values are what the quality checks exist to catch.
- **Dedup**: window-function rule keeps the latest copy of each `event_id`.
- **Completeness**: null `user_id` quarantined.
- **Ranges**: negative amounts, quantities <= 0, dates outside 2026-10-01 –
  2026-11-17.
- **Referential integrity**: `product_code` must exist in the product dimension.
- **Arithmetic**: `amount` must equal `quantity * unit_price` (within 0.01).
- **Reconciliation**: gold daily revenue must equal cleansed revenue grouped
  the same way (max diff 0.0).

## Results (real run, Nov 18, 2026)

```
raw=240 duplicates=4 quarantined=14 cleansed=222 gold=48 partitions=48
checks: 7/7 passed, reconciliation=PASS
```

- Raw rows: **240** (222 clean + 18 planted defects)
- Duplicates removed by window dedup: **4**
- Quarantined rows: **14** — null_user_id 5, negative_amount 3,
  unknown_product 3, date_out_of_range 2, amount_mismatch 1
- Cleansed rows: **222**; total cleansed revenue **$23,413.34**
- Gold aggregate rows: **48** (daily revenue by date / region / category)
- Curated partitions by `event_date`: **48**
- Quality checks: **7/7 PASS** (schema, completeness, uniqueness,
  non-negative amounts, arithmetic, referential integrity, reconciliation)

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py
python -m pytest -q
```

`run_pipeline.py` writes Parquet tables under `pipeline_tables/` (raw,
cleansed, quarantine, gold, plus `curated/` partitioned by `event_date`) and
a human-readable `validation_report.txt` in the project root.

## Added Nov 23, 2026 — Risk Technology ETL + agentic-AI quality triage

Added for a JPMorgan Chase Software Engineer III, Data Engineering role
(Risk Technology team, Databricks / Spark / Agentic AI). A second pipeline
in the same project, built on the same Spark patterns but over synthetic
risk-exposure trades instead of retail events:

- **`spark_pipeline/risk_data.py`** — seeded synthetic risk trades
  (`trade_id`, book, counterparty, instrument, notional, currency,
  trade date, exposure = notional × instrument risk factor). 150 clean
  rows + 15 planted defects (3 duplicates, 4 null counterparties,
  3 negative notionals, 2 unknown books, 2 future trade dates,
  1 exposure mismatch).
- **`spark_pipeline/risk_transforms.py`** — window-function dedup on
  `trade_id`, broadcast join to the 4-row book dimension, quality filter
  with quarantine, derived exposure bands, daily gold aggregates by
  trade date / book, and gold-vs-cleansed reconciliation.
- **`spark_pipeline/agentic_quality.py`** — agentic-AI-assisted triage
  of the quarantined rows: a deterministic, rule-based policy agent that
  observes each break, proposes a disposition (AUTO_FIX / ESCALATE /
  DROP), and verifies any recomputed value. The exposure-mismatch row is
  auto-fixed by recomputing exposure from notional × factor; missing
  counterparties, negative notionals and unknown books escalate to a
  human owner; out-of-window trade dates are dropped for re-ingest.
  No live LLM is called — the policy engine stands in for the agent's
  reasoning step so every finding is reproducible and auditable.
- **`spark_pipeline/risk_pipeline.py` / `run_risk_pipeline.py`** — runs
  the risk ETL and writes Parquet tables under `risk_tables/` plus a
  human-readable `risk_validation_report.txt`.

### Risk results (real run, Nov 23, 2026)

```
raw=165 duplicates=3 quarantined=12 cleansed=150 gold=48 partitions=48
triage: {'AUTO_FIX': 1, 'ESCALATE': 9, 'DROP': 2}, reconciliation=PASS
```

- Cleansed notional **$3,702,665,119.14**; cleansed exposure **$104,778,899.76**
- Gold aggregate rows: **48** (daily notional / exposure by date / book)
- Curated partitions by `trade_date`: **48**
- Triage: 1 AUTO_FIX (exposure recomputed to $424,086.42), 9 ESCALATE, 2 DROP

### How to run the risk pipeline

```bash
pip install -r requirements.txt
python run_risk_pipeline.py
python -m pytest tests/test_risk.py -q
```
