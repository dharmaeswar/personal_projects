# Restaurant Order Streaming Pipeline

A portfolio project for a **Data Engineer III** role (McDonald's-style Global
Technology, Data & Analytics). It builds the data product a restaurant chain
needs: order events stream in from restaurants, are cleansed and modelled in
near real time, and land in a partitioned cloud warehouse with governance
around them.

**All data is synthetic and seeded (seed 7).** No real McDonald's order,
restaurant, or customer data is used, and nothing here describes a real
restaurant system or a production pipeline.

## Problem statement

Restaurant orders arrive continuously from drive-thru, counter, kiosk,
delivery and mobile channels. The raw stream is messy: producers re-deliver
events, some events arrive hours late, channels are spelled a dozen ways,
and a few rows are just wrong (negative quantities, unknown menu codes,
totals that do not match quantity × price). Downstream teams need trusted,
modelled tables — not the raw stream — with data-quality SLAs and
governance they can audit.

## What it does

| Module | McDonald's Data Engineer III duty it maps to |
|---|---|
| `order_stream/events.py` | **Kafka topic** — partitioned by restaurant, offsets, consumer-group commits; the stream real-time ingestion is modelled on |
| `order_stream/streaming.py` | **Spark Structured Streaming-style micro-batches** — running watermark, late-event quarantine, 15-minute tumbling-window aggregates per restaurant |
| `order_stream/quality.py` | **Data-quality functions from the posting** — cleansing, standardization, parsing, de-duplication (keep latest), mapping, hierarchy management (restaurant → market → region); bad rows quarantined with a reason, never dropped silently |
| `order_stream/warehouse.py` | **Cloud storage + data modelling** — fact table partitioned by `event_date`/`restaurant_id` (the S3 / GCS object layout), star schema (the Redshift / BigQuery model), SCD2 menu-item dimension |
| `order_stream/governance.py` | **Data security & governance** — metadata catalog (owner, source, classification, retention), master-data standards checks, quality SLAs (timeliness, completeness, accuracy), role-based access |
| `order_stream/pipeline.py` | **Orchestration + observability** — topic → micro-batches → quality → warehouse → governance report, with run state (batches, rows, quarantine counts) recorded for retry |

## Runs locally, without a Kafka broker or a Spark cluster

Kafka and Spark are not installed here, so the pipeline runs locally with an
in-memory Kafka-modelled topic and pandas. It does **not** pretend a cluster
run happened. Every operation names the Kafka / Spark operation it mirrors,
so the same code maps one-to-one onto a real streaming job — swap the
in-memory topic for a Kafka consumer and the pandas steps for Spark
Structured Streaming and the logic is unchanged. `requirements.txt` lists
only pandas, pyarrow, numpy, pytest.

| This project (local) | Real stack equivalent |
|---|---|
| `KafkaTopic` partitions + offsets + consumer groups | Apache Kafka topic, consumer group offsets |
| `split_batches` watermark + late quarantine | Spark Structured Streaming `withWatermark` + late-data sink |
| `run_micro_batch` windowed aggregates | `groupBy(window, restaurant_id)` |
| `cleanse` dedup / mapping / hierarchy | Spark `dropDuplicates`, `withColumn`, dimension joins |
| `write_fact` partitioned Parquet | S3 / GCS partitioned writes; Redshift / BigQuery star schema |
| `governance.py` catalog + SLAs | Metadata catalog, data-quality SLA monitoring |

## How to run

```bash
python run_pipeline.py
```

Demo run (seeded): **128 events produced → 120 clean → 5 quarantined**
(3 bad rows + 2 late arrivals), 4 micro-batches, 5 fact partitions written,
governance SLAs met (completeness 0.9756, accuracy 0.96, timeliness 0.9844),
topic lag 0 after commit.

```bash
python -m pytest tests/ -q   # 26 tests
```

## Layout

```
restaurant-order-streaming-pipeline/
  order_stream/
    events.py       synthetic order events + Kafka-modelled topic
    streaming.py    micro-batch engine, watermark, windowed aggregates
    quality.py      cleansing, standardization, dedup, mapping, hierarchy
    warehouse.py    partitioned Parquet writes, star schema, SCD2 dims
    governance.py   metadata catalog, master-data checks, SLAs, access
    pipeline.py     end-to-end orchestration + run state
  run_pipeline.py   demo entry point
  tests/            26 tests (events, quality, streaming, warehouse, governance, pipeline)
```

## Honest limits

- GCP stack (BigQuery, Dataflow/Beam, GCS, Cloud Functions/Run) is **not**
  demonstrated here — the warehouse layout is cloud-shaped (S3/GCS object
  layout, Redshift/BigQuery star schema) but runs on local Parquet, and the
  streaming engine mirrors Spark Structured Streaming without running it.
- Apache Flink / Beam are not used; the micro-batch engine is the
  Structured Streaming pattern only.
- No real restaurant, order, or customer data; everything is seeded.
