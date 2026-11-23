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

## Added Nov 21, 2026 — home-health episode data quality

Added for a Data Engineer II (Home Health) role, where the work is
ETL/ELT of episode and visit records into governed tables. One new
module, `lakehouse/home_health.py`, run with
`python run_home_health.py` — same pandas + Parquet approach as the
rest of the project, no Spark cluster involved.

- **Synthetic episodes and visits** — 40 home-health episodes
  (de-identified patient key, start/end dates, discharge status,
  diagnosis group) and ~200 visits (visit id, episode id, visit
  date, visit type, duration in minutes, clinician id), all seeded
  and reproducible. No real patient data anywhere.
- **Home-health quality rules** — completeness, uniqueness, duration
  ranges (0–480 minutes), referential integrity (every visit's
  episode must exist), plus a visit-window rule: every visit must
  fall inside its episode's start/end window. Episodes ending before
  they start are caught by a separate date-order check, so each bad
  row is owned by exactly one check.
- **Quarantine, not silent drops** — bad visits go to a quarantine
  table with the failing check named per row; the gold episode
  summary (visit count, total and average minutes per episode) is
  built only from clean silver visits and reconciles back to silver.

The fixture plants 9 bad rows on purpose (2 duplicate visit ids,
2 null episode ids, 1 visit outside its episode window, 1 negative
duration, 1 unknown episode id, 1 duration over the 480-minute cap,
1 episode ending before it starts).

## Results of the home-health run (real run, Nov 21, 2026)

```
Episodes: 40; visits (bronze): 202
Episode checks: 2/3 passed (1 fails as designed — the bad episode)
Visit checks: 0/5 passed (5 fail as designed — the 8 planted bad visits)
Silver visits: 194; quarantined: 8; gold episode summary rows: 40
Total silver minutes: 13341; gold total minutes: 13341
Reconciliation: PASS
```

Tests: **45 passed** (`python -m pytest -q`) — 33 earlier tests plus
12 new tests for episode/visit generation, every violation type,
quarantine counts, gold reconciliation and determinism
(`tests/test_home_health.py`).

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py
python run_orchestrated.py [--run-id daily]
python run_home_health.py
python run_talent.py
python -m pytest -q
```

`run_pipeline.py` writes Parquet tables under `lakehouse_tables/` and a
human-readable `validation_report.txt` in the project root.
`run_orchestrated.py` runs the same pipeline as a DAG, snapshots silver
and gold under `lakehouse_tables/snapshots/`, and writes
`orchestration_report.txt`.
`run_home_health.py` runs the episode/visit pipeline and writes
`home_health_report.txt`.
`run_streaming.py` runs the micro-batch streaming ingest and the
observability monitors, writing `streaming_report.txt` and
`observability_report.txt`.

## Added Nov 23, 2026 — streaming ingest and data observability

Two modules added for a Capital One Data Engineer 5 role (Python +
Spark, Databricks/Snowflake, lakehouse, streaming, observability):

- **Streaming ingest** (`lakehouse/streaming.py`) — micro-batch
  processing in the spirit of Spark Structured Streaming: an
  append-only event stream, watermark handling for late data, and
  exactly-once delivery via dedup on `event_id` against a checkpoint.
  The demo stream plants 3 duplicate deliveries and 2 late events;
  the run accepts 120 events, drops 2 late and 3 duplicates, and
  re-processing a batch is a no-op. Run it with `run_streaming.py`.
- **Data observability** (`lakehouse/observability.py`) — freshness,
  volume-anomaly, and schema-drift monitors in the spirit of Monte
  Carlo: freshness alerts when the newest data passes its SLA,
  volume alerts on a z-score against prior daily totals, schema drift
  alerts on missing columns and warns on extra columns. Monitors
  never raise on bad data; an alert is a result, not an error.
  The same run writes `observability_report.txt`.

Tests: **60 passed** (`python -m pytest -q`) — 45 earlier tests plus
7 streaming tests (`tests/test_streaming.py`) and 8 observability
tests (`tests/test_observability.py`).

## Added Nov 23, 2026 — talent data foundations

One module added for an Amazon Data Engineer (Talent Solutions, ITDS
Data Foundations) role, where the work is streaming and batch ingestion
that unifies talent service domains into a cross-cutting talent data
model vended for analytics and operational use. New module
`lakehouse/talent.py`, run with `python run_talent.py` — same pandas +
Parquet approach as the rest of the project, no Spark cluster, Kinesis
stream, or Redshift warehouse is involved, and the code says so where
it matters.

- **Streaming ingest** — 120 synthetic talent change events
  (employee / role / skill / learning updates) processed exactly once
  by reusing the shared streamer: 3 duplicate deliveries and 2 late
  events dropped at the watermark, checkpoint offset 124.
- **Batch ingest** — a nightly learning-records batch of 182 rows,
  deduplicated on `record_id` (180 loaded, 2 duplicates dropped).
- **Unified talent model** — one row per clean employee (59): current
  role and department, skill list, learning count, last learning date,
  average score. Built only from silver rows; 2 silver learning rows
  belonging to the quarantined employee are held back, not vended.
- **Vended views** — an analytics view (5 departments: headcount,
  average skills, average learning, learning coverage) and an
  operational view (one row per employee) for downstream integrations.
  Both reconcile back to the unified model and silver learning.
- **Quality checks** — completeness, uniqueness, score ranges,
  referential integrity, plus a talent rule: no learning record may
  predate the employee's hire date. The fixture plants 8 bad rows
  (2 duplicate record ids, 2 null employee ids, 1 unknown employee,
  1 learning before hire, 1 unknown skill, 1 unknown role);
  7 learning rows and 1 employee are quarantined with reasons.
- **Query tuning** — a per-employee full-table scan loop versus a
  single group-by over 50,050 rows: 152.4 ms vs 3.7 ms, a 41.0x
  speedup, with identical per-employee averages.

Tests: **70 passed** (`python -m pytest -q`) — 60 earlier tests plus
10 new tests for domain shapes, every violation type, quarantine
counts, the unified model, view reconciliation, streaming
exactly-once, batch dedup, tuning results and determinism
(`tests/test_talent.py`).

## Added Nov 23, 2026 — workforce data architecture

One module added for an Amazon Data Engineer III (Workforce Solutions)
role, where the work is owning the data architecture behind hiring
processes, career mobility and workforce engagement: scalable ETL
pipelines, data modeling, warehousing, best practices, mentoring
standards and evaluating generative AI integrations. New module
`lakehouse/workforce.py`, run with `python run_workforce.py` — same
pandas + Parquet approach as the rest of the project, no Spark
cluster, Kinesis stream, or Redshift warehouse is involved, and the
code says so where it matters.

- **Streaming ingest** — 120 synthetic hiring change events
  (requisition / candidate / interview / offer updates) processed
  exactly once by reusing the shared streamer: 3 duplicate deliveries
  and 2 late events dropped at the watermark, checkpoint offset 124.
- **Batch ingest** — a nightly engagement-survey batch of 120 rows
  (60 employees x 2 quarters), deduplicated on `survey_id`.
- **Unified workforce model** — one row per requisition (15): the
  hiring funnel (candidates, interviews, offers, hires), time to
  fill, and offer-accept rate. Built only from silver rows; 88
  vendable candidates.
- **Vended views** — an analytics view (5 departments: requisitions,
  hires, average time to fill, offer-accept rate, average engagement,
  internal moves) and an operational view (one row per requisition)
  for downstream integrations. Both reconcile back to the unified
  model and silver candidates.
- **Quality checks** — completeness, uniqueness, score ranges,
  referential integrity, plus three workforce rules: no interview may
  predate the application, no offer may exist for a candidate with no
  interview, and no internal move may predate the hire date. The
  fixture plants 8 bad rows (2 duplicate candidate ids, 1 null req
  id, 1 unknown requisition, 1 early interview, 1 offer without an
  interview, 1 move before hire, 1 out-of-range engagement score);
  4 candidates, 1 interview, 1 offer, 1 move and 1 survey are
  quarantined with reasons.
- **GenAI-assist evaluation** — the module scores a deterministic,
  seeded stand-in rule proposer (no real LLM call is made) against
  the planted violations: 8 rules proposed, 5 true, precision 0.625,
  recall 0.714 (5 of 7 violation types caught), 3 spurious rules
  rejected. A human stays in the loop: only evaluated rules are
  adopted.
- **Query tuning** — a per-requisition full-table scan loop versus a
  single group-by over 50,072 rows: 44.3 ms vs 4.4 ms, a 10.1x
  speedup, with identical per-requisition averages.

Tests: **81 passed** (`python -m pytest -q`) — 70 earlier tests plus
11 new tests for domain shapes, every violation type, quarantine
counts and reasons, the unified model, view reconciliation, streaming
exactly-once, batch dedup, the GenAI-assist evaluation, tuning
results and determinism (`tests/test_workforce.py`).

## Added Nov 23, 2026 — central InfraOps analytics

One module added for an Amazon Data Engineer (Central InfraOps
Analytics Team) role, where the work is the data foundation behind
AWS's global data-center operations: ETL pipelines that ingest
infrastructure signals into the warehouse and lake, data models that
drive physical design, quality measures and monitoring that keep the
data trusted. New module `lakehouse/infraops.py`, run with
`python run_infraops.py` — same pandas + Parquet approach as the rest
of the project, no Spark cluster, Kinesis stream, or Redshift
warehouse is involved, and the code says so where it matters.

- **Streaming ingest** — 120 synthetic telemetry change events
  (power, temperature, humidity, utilization readings) processed
  exactly once by reusing the shared streamer: 3 duplicate deliveries
  and 2 late events dropped at the watermark, checkpoint offset 124.
- **Batch ingest** — a nightly incident batch of 24 rows,
  deduplicated on `incident_id` (24 loaded, 0 duplicates dropped).
- **Unified infra model** — one row per data center (8): telemetry
  aggregates (average temperature, maximum utilization, total power),
  incident counts and latest capacity utilization. Built only from
  silver rows; 236 vendable telemetry rows.
- **Vended views** — an analytics view (4 regions: data centers,
  average temperature, peak utilization, incidents, average capacity
  use) and an operational view (one row per data center) for
  dashboards and APIs. Both reconcile back to the unified model and
  silver telemetry.
- **Quality checks** — completeness, uniqueness, value ranges,
  referential integrity, plus three infra rules: no incident may
  resolve before it opened, no equipment may be decommissioned
  before it was installed, and every telemetry row must name the
  data center its equipment belongs to. The fixture plants 8 bad
  rows (2 duplicate reading ids, 1 null data center, 1 unknown
  equipment, 1 temperature of 52 C, 1 utilization of 112%, 1
  incident resolved before opening, 1 equipment decommissioned
  before installation); 6 telemetry rows, 1 incident and 1
  equipment item are quarantined with reasons.
- **Query tuning** — a per-data-center full-table scan loop versus a
  single group-by over 50,032 rows: 7.1 ms vs 1.0 ms, a 7.5x
  speedup, with identical per-data-center averages.

Tests: **91 passed** (`python -m pytest -q`) — 81 earlier tests plus
10 new tests for domain shapes, every violation type, quarantine
counts and reasons, the unified model, view reconciliation, streaming
exactly-once, batch dedup, tuning results and determinism
(`tests/test_infraops.py`).

## Added Nov 23, 2026 — backend warehouse load (Kafka-style ingest, Snowflake-style staged MERGE)

Added for a JPMorgan Chase Software Engineer III, Backend Data Engineer role
(Req 210747185), where the work is scalable data pipelines, ETL, data
warehouses and ML platform enablement on AWS, Databricks and Spark. One new
module, running locally with pandas + Parquet — no Kafka broker or Snowflake
account is involved, and the code says so where it matters.

- **Event ingest** (`lakehouse/warehouse.py`, run with
  `python run_warehouse.py`) — a Kafka-style consumer polls the event
  stream in micro-batches, commits offsets per batch, and drops redelivered
  events on `event_id` (exactly-once). Bad rows are quarantined with a
  reason (unknown customer, non-positive quantity) instead of being staged.
- **Staged load** — valid events land in a staging table as Parquet plus a
  manifest (rows staged, source, load time), the way Snowflake `COPY INTO`
  loads files into a staging table.
- **Star-schema warehouse** — SCD Type 2 customer and product dimensions
  (a changed attribute closes the current version and opens a new one with
  the next surrogate key; unchanged rows are left alone) and an order fact
  table loaded by an idempotent `MERGE` on `order_id`: re-running the same
  batch inserts 0 rows.
- **Reconciliation** — fact revenue must equal staged valid-event revenue
  within 0.01; any gap means the MERGE lost or duplicated rows.

## Results of the warehouse run (real run, Nov 23, 2026)

```
Events received: 160 (150 base + 5 Kafka redeliveries + 5 bad rows)
Duplicates dropped: 5, micro-batches polled: 4, committed offset: 159
Quarantined: 5 (3 unknown customer, 2 non-positive quantity)
Rows staged: 150
Customer dim (SCD Type 2): 20 inserted; product dim: 8 inserted
Fact orders inserted: 150 (0 skipped)
Reconciliation: staged revenue 31889.39 vs fact revenue 31889.39 (difference 0.00)
Reconciled: YES
```

Tests: **106 passed** (`python -m pytest -q`) — 91 earlier tests plus
15 new tests for event generation, consumer dedup and offset commit, resume
from state, quarantine counts and reasons, staged load, SCD Type 2
close/reopen, fact MERGE idempotency, reconciliation, determinism and
consumer-state round-tripping (`tests/test_warehouse.py`).
