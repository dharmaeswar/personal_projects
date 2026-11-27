# Commissioning Data ETL Platform

A Python ETL platform for facility-commissioning data: it pulls
commissioning-system records and work tickets from paginated REST APIs,
validates and loads them into a warehouse, runs data-quality checks, and
publishes dashboard-ready aggregates (commissioning progress, ticket aging,
open defects).

Built as a portfolio project for a Commissioning Data Engineer application
(SQL + Python, ETL from APIs, dashboards, Azure-shaped ticketing, automation).
All source data is synthetic and seeded; nothing here describes a real
facility, system, or ticket.

## Problem statement

A commissioning team tracks hundreds of systems (electrical, mechanical,
HVAC, controls) through checkpoints, and the defects found along the way
live as tickets in a ticketing system. The data arrives from two APIs that
page, occasionally fail transiently, and sometimes re-deliver records. The
team needs one trusted warehouse: every row validated, duplicates collapsed,
bad rows quarantined with a reason, and dashboards that answer — how far
along is each system, which tickets are aging, where are the open defects —
without anyone touching raw API payloads.

## What it does

- **API clients** (`commissioning_etl/api_client.py`) — paginated clients
  for the commissioning-systems API and the ticketing API, with retry and
  backoff on transient failures and a fetch-all that walks every page.
- **ETL** (`commissioning_etl/etl.py`) — extract from both APIs, transform
  (normalize, validate, dedupe by id keeping the newest `updated_at`),
  load into SQLite: bronze staging tables plus marts. Loads are
  incremental: a watermark means a re-run inserts 0 new rows.
- **Quality** (`commissioning_etl/quality.py`) — 11 checks that block
  publish: row counts, nulls in key columns, completed <= total
  checkpoints, ticket-to-system references, duplicate counts, freshness
  SLA, and ticket-age SLA reporting.
- **Dashboards** (`commissioning_etl/dashboards.py`) — dashboard datasets:
  commissioning progress by system and area, ticket aging buckets by
  priority, open-defect list, plus a plain-text daily report.
- **Automation** (`run_pipeline.py`) — one command runs extract → load →
  checks → dashboards, writes `output/dashboard_summary.json`, and exits
  non-zero if any quality check fails.

## Layout

```
commissioning_etl/
  api_client.py    paginated API clients, retry/backoff, fetch-all
  etl.py           extract / transform / load, watermarked incremental loads
  quality.py       data-quality checks that gate the dashboard publish
  dashboards.py    progress, ticket-aging, open-defect aggregates + report
data/
  commissioning_systems.json   12 systems (+1 re-delivered duplicate, 1 invalid)
  tickets.json                 24 tickets (+1 duplicate, 1 missing field, 1 orphan)
run_pipeline.py    end-to-end run: ETL -> checks -> dashboards
tests/             16 pytest tests
```

## Run it

```bash
pip install -r requirements.txt   # pytest only; the pipeline is stdlib
python run_pipeline.py
pytest -q
```

Seeded run: 13 system records received / 1 duplicate collapsed / 1
quarantined (completed checkpoints exceed total); 26 ticket records / 1
duplicate collapsed / 2 quarantined (missing priority, unknown system).
Warehouse: 11 systems, 23 tickets. 11/11 quality checks pass.
Dashboards: 11 systems tracked, 197/280 checkpoints complete (70.4%);
23 tickets, 15 open or in progress, 3 past the 30-day age SLA.

## Honest limits

- The "APIs" are local JSON fixtures behind a paginated client, not live
  HTTP services; the client models pagination, transient failure, and
  retry, but there is no network, auth, or real Azure service behind it.
- The warehouse is SQLite, not Azure SQL / Synapse; the schema names the
  Azure shape each table mirrors (staging, marts, watermark) so the
  mapping is explicit.
- The ticketing feed models an Azure DevOps-style work-item API (id,
  title, state, priority, area, system reference); it is a demo model,
  not a real Azure DevOps project.
- Dashboards are JSON datasets plus a text report, not a Power BI file;
  the aggregates are the exact rows a dashboard would bind to.
