# Media Session Streaming Pipeline

A portfolio project for a Senior Product Software Engineer, Data Processing
role (media session data on Databricks / Spark Structured Streaming). It
builds the data product the role asks for over synthetic playback-session
events: events stream in, are cleansed and sessionized in micro-batches,
and land in a bronze → silver → gold lakehouse with governance and a cost
advisor — orchestrated the way an Airflow / Databricks Workflows job
would run it.

**All data is synthetic and seeded (seed 42).** No real streaming-service
session, user, or title data is used, and nothing here describes a real
platform's traffic or a production pipeline.

## Runs locally, without a Spark cluster or a Databricks workspace

Spark, Databricks, and AWS are not installed here, so the pipeline runs
locally with pandas + Parquet and the API-free config builders emit JSON.
It does **not** pretend a cluster or cloud run happened. Every pandas
operation names the Spark operation it mirrors, so the same code maps
one-to-one onto a real PySpark / Structured Streaming job on Databricks.

## Problem statement

Playback-session events (start, heartbeat, pause, seek, ad break, error,
end) arrive continuously from TV, mobile, web, and tablet. The raw stream
is messy: producers re-deliver events, some arrive late, a few rows are
just wrong (negative playheads, unknown event types, impossible bitrates).
Downstream teams need trusted session tables — not the raw stream — with
data-quality SLAs, lineage, and governance they can audit, plus a job
that stays cheap as volume grows.

## What it does

| Module | Role duty it maps to |
|---|---|
| `session_stream/events.py` | **Ingestion** — seeded synthetic session events; a Kafka-style partitioned topic with offsets and consumer-group commits |
| `session_stream/quality.py` | **Data quality** — required-field, type, range and playhead checks; bad rows quarantined with a reason, never dropped silently; dedupe on `event_id` |
| `session_stream/streaming.py` | **Spark Structured Streaming** — watermark (10-min lateness) splitting on-time vs late events; session windows with a 30-min gap; 15-min tumbling aggregates per title |
| `session_stream/warehouse.py` | **Delta Lake medallion** — bronze / silver / gold Parquet writes partitioned by date and title; SCD2 title dimension; star-schema session fact |
| `session_stream/governance.py` | **Unity Catalog** — `catalog.schema.table` registry, PII column tagging, column lineage, audit log; user IDs hashed before gold |
| `session_stream/cost.py` | **Cluster & cost optimization** — target 128 MB files, skew detection (max/median partition ratio), DBU cost estimate, tuning advice |
| `session_stream/pipeline.py` | **Orchestration** — Airflow-style DAG with retries and dependency order; Databricks Workflows job spec (job cluster, autoscale, schedule) |

## Spark / Databricks mapping

| This project (pandas) | Databricks / Spark equivalent |
|---|---|
| `apply_watermark` — max event time minus lateness | `withWatermark("event_ts", "10 minutes")` |
| `sessionize` — gap split per session_id | session windows with `gapDuration("30 minutes")` |
| `tumbling_aggregates` — floor to 15-min window | `groupBy(window("event_ts", "15 minutes"), "title_id")` |
| `cleanse` dedupe on event_id | `dropDuplicates(["event_id"])` |
| bronze / silver / gold Parquet writes | `df.write.partitionBy(...).format("delta")` |
| `Catalog` registry + lineage | Unity Catalog + Delta Lake `DESCRIBE HISTORY` |
| `advise` partition / skew / cost checks | Spark UI stage metrics + DBU usage reports |

## Run it

```bash
python -m pytest -q            # tests
python run_pipeline.py          # full run; writes data/ + run_manifest.json
```

## Layout

```
session_stream/
  events.py       synthetic event generator + Kafka-style topic
  quality.py      data-quality checks + quarantine
  streaming.py    watermark, session windows, tumbling aggregates
  warehouse.py    bronze/silver/gold writes, SCD2 dimension, fact table
  governance.py   Unity Catalog-style registry, lineage, PII masking
  cost.py         partition sizing, skew detection, DBU cost estimate
  pipeline.py     Airflow-style DAG + Databricks Workflows job spec
tests/            pytest suite (one file per module)
run_pipeline.py   CLI entry point
```
