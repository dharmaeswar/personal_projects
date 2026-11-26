# Personalization Training Datasets Pipeline

A portfolio project for a **Senior Data Engineer, News & Entertainment ML**
role (Disney-style). It builds the versioned ML training datasets a
personalization team trains on: raw content-interaction events become
cleansed silver tables, point-in-time-correct training rows, and a
star-schema gold layer — orchestrated as a daily Airflow / Databricks
Workflows job and registered in the AWS Glue Data Catalog.

**All data is synthetic and seeded (seed 42).** No real viewer, title, or
platform data is used, and nothing here describes a real company's traffic
or a production pipeline.

## Runs locally, without Spark, Databricks, or AWS

PySpark, Databricks, and AWS are not installed here, so the pipeline runs
locally with pandas + Parquet. It does **not** pretend a cluster or cloud
run happened. Every pandas operation names the Spark operation it mirrors,
so the same logic maps one-to-one onto a real PySpark job on Databricks.

## Problem statement

A personalization model is only as good as its training data. Raw
interaction events (impressions, view starts, completions, likes, shares,
skips) arrive messy: producers re-deliver events, some rows are just wrong
(negative watch times, unknown event types), and the obvious way to build
labels — "did this user ever complete this title?" — leaks the future into
training and flatters the model offline. Downstream ML engineers need
training datasets they can trust: deduplicated, quality-gated, labelled
from a fixed horizon, split by time, versioned with a fingerprint, and
cheap to rebuild every day.

## What it does

| Module | Role duty it maps to |
|---|---|
| `personalization_data/events.py` | **Ingestion** — seeded synthetic interaction events (impression → view → complete / like / share / skip) with ~2% producer re-deliveries |
| `personalization_data/quality.py` | **Data quality** — schema/contract checks; bad rows quarantined with a reason, never dropped silently; dedupe on `event_id` keeping the latest ingest |
| `personalization_data/features.py` | **Training rows** — one labelled row per impression; labels from events inside a 24h horizon only; history features from events strictly *before* the impression (no leakage) |
| `personalization_data/datasets.py` | **Splits & medallion** — time-based train / validation / test split; bronze / silver / gold Parquet partitioned by date; version manifest with a SHA-256 fingerprint |
| `personalization_data/modeling.py` | **Data modeling** — star schema: `fact_interactions`, `dim_user`, SCD Type 2 `dim_content`, `dim_date` |
| `personalization_data/orchestration.py` | **Orchestration** — Airflow-style DAG with retries and skip-on-upstream-failure; Databricks Workflows job spec; AWS Glue Data Catalog entries |
| `personalization_data/cost.py` | **Cost & performance** — partition-skew detection, 128 MB target file sizing, DBU cost estimate, tuning advice |

## Spark / Databricks mapping

| This project (pandas) | Databricks / Spark equivalent |
|---|---|
| `cleanse` dedupe on `event_id` | `dropDuplicates(["event_id"])` after ordering by `ingested_at` |
| `build_training_rows` as-of history | `rangeBetween` window functions; time-bounded self-join for labels |
| `time_split` by impression date | `WHERE impression_date < ...` train / val / test partitions |
| bronze / silver / gold Parquet writes | `df.write.partitionBy(...).format("delta")` |
| `dataset_fingerprint` manifest | Delta Lake `DESCRIBE HISTORY` + time travel |
| `apply_content_change` SCD2 | Delta `MERGE` closing the current row, opening a new one |
| `DagRun` tasks + retries | Airflow DAG / Databricks Workflows multi-task job |
| `glue_catalog` table entries | AWS Glue Data Catalog / Athena tables |

## Run it

```bash
python -m pytest -q            # tests
python run_pipeline.py         # full run; writes data/bronze, data/silver, data/gold
python run_pipeline.py --impressions 800 --out data
```

## Local run (Nov 26, 2026)

```text
raw events:          1007 (400 impressions + follow-ons + redeliveries)
clean events:        987 (dedupe removed 20 re-deliveries, 0 quarantined)
training rows:       400 (one per impression)
label rates:         40.0% completed, 14.0% liked
splits:              train 284 / validation 58 / test 58 (time-based)
star schema:         dim_user 114, dim_content 60, dim_date 14, fact 987
dataset fingerprint: 5b8c16b3eccf68a4
DAG:                 all 6 tasks success
cost advice:         partition sizes balanced; no tuning action needed
```

## Honesty note

The pipeline runs on synthetic data with pandas, not on a Spark cluster.
DBU figures are estimates from local row counts, not a real cloud bill.
The S3 locations in the Glue catalog are placeholders for where the
tables would live in production.
