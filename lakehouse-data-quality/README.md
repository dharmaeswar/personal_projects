# Lakehouse Data Quality

A portfolio project for a Data Engineer / Databricks Engineer role. It builds a
small medallion lakehouse (bronze → silver → gold) the way a Databricks /
Delta Lake pipeline would, and validates every layer the way a data-quality
team would: schema enforcement, completeness, uniqueness, ranges, referential
integrity, and reconciliation of gold aggregates back to silver.

**All data is synthetic and seeded.** No real company, customer, or order data
is used, and nothing here is a claim about any real institution.

## How it maps to Databricks / Delta Lake

Databricks itself is a managed Spark runtime, so this project runs locally
with pandas + Parquet instead of a Spark cluster. The patterns are the same
ones a Databricks job uses:

- **Bronze** — raw ingest, stored as Parquet, append-only. Nothing is cleaned
  here, so bad source rows are visible.
- **Silver** — cleaned, deduplicated, type-checked tables. Bad rows are moved
  to a quarantine table instead of being dropped silently.
- **Gold** — business aggregates (daily revenue by region and product
  category) built only from silver.
- **Delta-style transaction log** — every write appends a versioned entry to
  `_delta_log.json` (version, operation, rows added, rows removed), so any
  table can be traced back to the write that produced it.
- **Schema enforcement** — each table has an expected schema (column, type,
  nullable). Writes that violate it are rejected before they land.

## What it validates

- **Schema**: column presence, dtypes, nullability per table.
- **Completeness**: null rates per column, with a threshold per check.
- **Uniqueness**: duplicate primary keys (order_id, customer_id, product_id).
- **Ranges**: quantity > 0, unit_price >= 0, order dates inside the allowed window.
- **Referential integrity**: every order's customer_id and product_id must exist.
- **Arithmetic**: total_amount must equal quantity * unit_price (within 0.01).
- **Reconciliation**: gold daily revenue must equal silver revenue grouped the
  same way (within 0.01).

The bronze fixture plants 13 bad rows on purpose (3 duplicate order ids,
4 null customer ids, 2 negative quantities, 2 unknown product ids, 1 future
order date, 1 wrong total). The pipeline must quarantine all 13 and the
report must list each violation type with its count.

## Added Nov 18, 2026 — workflow orchestration and Iceberg-style snapshots

Added for a Senior Data Engineer (Tech Foundations) role, where the work
is large-scale data systems, data modeling, workflow orchestration and
table formats. Two new modules, both running locally with pandas +
Parquet — no Spark cluster, Airflow service or Iceberg runtime is
involved, and the code says so where it matters.

- **Workflow orchestration** (`lakehouse/orchestration.py`, run with
  `python run_orchestrated.py`) — the pipeline as a DAG of five tasks
  (ingest → validate → silver → gold → reconcile/report) with named
  dependencies, topological ordering, cycle/unknown-dependency checks,
  retries for transient failures only, and resume: a re-run with the
  same run id skips tasks that already succeeded with the same inputs
  instead of redoing them. Each task reads its inputs from the lakehouse
  tables on disk, so resume works from persisted state. A failed task
  marks the run failed and its downstream tasks are skipped, never run
  on stale inputs. The same DAG maps onto Airflow: each task becomes an
  operator and `depends_on` becomes `>>`.
- **Iceberg-style snapshots** (`lakehouse/snapshots.py`) — every silver
  and gold build commits an immutable snapshot (snapshot id, parent id,
  operation, schema version, row count, columns) to a manifest
  registry. `read_snapshot` is time travel: any earlier state of a table
  reads back exactly as written. `evolve_schema` adds a nullable column
  with a default, bumps the schema version, and never rewrites history.
  A failed write never touches the registry, so it is never observed
  as committed.

## Results of the orchestrated run (real run, Nov 18, 2026)

```
DAG RUN daily-2026-11-18: SUCCEEDED
ingest_bronze, validate_bronze, build_silver, build_gold, reconcile_report:
  5/5 succeeded, 1 attempt each
Re-run with the same run id: 5/5 skipped (already succeeded, same inputs)
silver snapshot 1: 187 rows; gold snapshot 1: 185 daily groups
Bronze checks 2/8 passed (6 fail as designed — the 13 planted bad rows);
  13 rows quarantined; reconciliation PASS
```

Tests: **33 passed** (`python -m pytest -q`) — 19 original lakehouse
tests plus 14 new tests for DAG ordering, retries, resume, failure
skips, snapshot chains, time travel and schema evolution
(`tests/test_orchestration_snapshots.py`).

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py
python run_orchestrated.py [--run-id daily]
python -m pytest -q
```

`run_pipeline.py` writes Parquet tables under `lakehouse_tables/` and a
human-readable `validation_report.txt` in the project root.
`run_orchestrated.py` runs the same pipeline as a DAG, snapshots silver
and gold under `lakehouse_tables/snapshots/`, and writes
`orchestration_report.txt`.
