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
