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

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py
python -m pytest -q
```

`run_pipeline.py` writes Parquet tables under `lakehouse_tables/` and a
human-readable `validation_report.txt` in the project root.
