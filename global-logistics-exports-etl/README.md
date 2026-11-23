# Global Logistics Exports ETL

An end-to-end data-engineering pipeline for cross-border export shipments, built
for the Amazon Data Engineer I (Global Logistics Exports) role. It ingests raw
export manifests, validates every record, converts values to USD, and loads a
star-schema warehouse that analysts can query for trade and logistics reporting.

## What it does

1. **Extract** — reads export manifest CSVs (shipment id, ship date, origin,
   destination country, HS product code, value, currency, weight, customs status)
   and an FX rates table.
2. **Validate** — applies data-quality rules; bad rows are quarantined with a
   reason code instead of silently dropped or loaded.
3. **Transform** — converts values to USD, normalises HS codes and dates.
4. **Load** — upserts dimension tables (country, product, date) and loads the
   `fact_exports` table in SQLite. Loads are incremental (watermark on ship
   date) and idempotent (re-running the same manifest loads nothing twice).

## Layout

- `exports_etl/ingest.py` — CSV manifest and FX-rate readers.
- `exports_etl/quality.py` — data-quality rules and quarantine reasons.
- `exports_etl/fx.py` — currency conversion to USD.
- `exports_etl/warehouse.py` — star-schema DDL, incremental load, reports.
- `exports_etl/pipeline.py` — orchestration: extract, validate, transform, load.
- `run_pipeline.py` — CLI entry point.
- `data/` — sample manifests (20 rows, 3 intentionally bad) and FX rates.

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py --manifest data/sample_manifests.csv --rates data/fx_rates.csv --db exports.db
python -m pytest -q
```

The sample run loads 17 of 20 rows, quarantines 3 (duplicate shipment id,
negative value, unknown currency), and reports total export value in USD.

## Design notes

- Money uses `Decimal`, never float, so USD totals are exact.
- The warehouse is a star schema: `fact_exports` joins `dim_date`,
  `dim_country`, and `dim_product` (HS code). Queries for monthly value by
  country and top products by value are included.
- Incremental load: a watermark table records the latest ship date loaded;
  re-running a manifest is a no-op for already-loaded shipment ids.
