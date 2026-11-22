# Manufacturing Telemetry Data Platform

A Python data platform for additive-manufacturing machine telemetry:
WAAM printers and weld-repair robots stream readings, the platform
abstracts four storage technologies behind one write path, and a
reporting API serves analytics over the stored data.

Built as a portfolio project for a Senior Software Engineer, Data and ML
application (distributed data platform, data technology abstraction and
APIs, analytics/reporting architectures, data modeling, cloud and on-prem
services). All telemetry is synthetic and seeded; nothing here describes
a real factory, machine, or production run.

## Problem statement

A manufacturing platform has to take in fast telemetry from many
machines, keep it in the right store for each access pattern, and answer
questions about it — what ran hot, which machine shook, how a run
performed — without every reader touching raw tables. One store cannot
do all of that well: time-series reads want an append-only log,
configuration wants documents, the latest reading wants a cache, and
runs and jobs want relations.

## What it does

- **Stream** (`telemetry_platform/stream.py`) — a partitioned,
  append-only topic modelled on Kafka: producers publish by machine id,
  consumer groups track their own committed offsets, lag is measurable.
- **Stores** (`telemetry_platform/stores.py`) — one `DataPlatform`
  facade routes each reading to four stores behind a single interface:
  time-series measurements and runs in SQLite (InfluxDB / PostgreSQL
  shape), machine configuration documents in memory (MongoDB shape),
  latest reading per machine in a TTL cache (Redis shape).
- **Analytics** (`telemetry_platform/analytics.py`) — per-machine
  summaries (mean/max temperature, vibration, weld current, layers),
  anomaly flags with plain-language reasons (over-temperature,
  vibration spike, weld current out of band, 3-sigma temperature
  outlier), and a daily report that rolls them up.
- **API** (`telemetry_platform/api.py`) — `get_machine_summary`,
  `list_anomalies`, `get_daily_report`, `latest_reading`, and a JSON
  report export, so dashboards ask the platform instead of the tables.

## Layout

```
telemetry_platform/
  stream.py      partitioned topic, consumer groups, offsets
  stores.py      time-series / document / cache / relational stores
  analytics.py   summaries, anomaly flags, daily report
  api.py         reporting API over the platform
run_demo.py      seeds 720 synthetic readings, streams them, prints report
tests/           10 pytest tests
```

## Run it

```bash
pip install -r requirements.txt
python run_demo.py
pytest -q
```

Demo run (seed 42): 720 readings across 3 machines, 2 seeded events —
an over-temperature reading on WAAM-01 and a vibration spike on
WELD-01 — both found by the anomaly flags in the daily report.

## Honest limits

- Stores are SQLite and in-memory dicts, not a real InfluxDB, MongoDB,
  Redis, or PostgreSQL cluster; the code names the real store each
  abstraction mirrors so the mapping is explicit.
- The stream is in-process, not a Kafka broker: same partition, offset,
  and consumer-group semantics, no network or replication.
- No ROS, robotics, or additive-manufacturing domain claims: the
  telemetry shape (temperature, vibration, weld current, layer) is the
  demo's own model of a print run.
```

