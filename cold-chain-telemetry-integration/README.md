# Cold-Chain Telemetry Integration

A portfolio project for a **Senior Data Integration Engineer** role in
temperature-controlled logistics. It builds the ingestion pipelines the
role describes: device telemetry, carrier milestones, and customer order
data, mapped into shared shipment and telemetry models, validated, and
loaded — with monitoring, alerts, and replay/backfill.

**All data is synthetic and seeded.** No real company, customer, shipment,
or order data is used, and nothing here is a claim about any real
institution.

## What it does

- **Ingestion from four source shapes** — device telemetry as JSON lines
  (API / webhook / queue), carrier milestones as CSV (SFTP file drop),
  customer orders as a JSON array (API poll), in batches of 100.
- **Configuration-driven mapping** — partner specs live in
  `configs/partners.json`: field maps, timestamp formats, and temperature
  units (including a Fahrenheit partner converted to Celsius). Adding a
  partner means adding a config entry, not new code.
- **Normalisation into shared models** — every source maps into one
  `Shipment`, `TelemetryReading`, or `Milestone` shape, so downstream
  checks only ever see one schema.
- **Validation and quarantine** — temperature excursions against each
  product's allowed range, physically impossible temperatures, duplicate
  ids, unknown shipment ids, unknown milestone events, bad timestamps,
  and missing fields. Failed rows are quarantined with a reason, never
  dropped silently and never blocking the batch.
- **Monitoring and alerts** — run summary with per-source counts,
  quarantine rate, temperature-excursion alerts, and late-data alerts.
- **Replay and backfill** — loads are idempotent on reading/milestone id,
  so re-running a date window never double-counts; `replay_window`
  filters raw feeds to one ship-date window.

## Demo run (seed 42, deterministic)

```
python3 run_pipeline.py
```

| Measure | Value |
|---|---|
| Shipments | 240 |
| Telemetry readings (raw) | 1,200 |
| Readings quarantined at normalise (bad timestamp / missing temperature) | 22 |
| Readings normalised | 1,178 |
| Readings quarantined by quality checks (43 excursions, 8 duplicates) | 51 |
| Readings loaded | 1,126 |
| Carrier milestones loaded | 960 |
| Quarantine rate | 2.39% |
| Temperature-excursion alerts | 43 |

## Tests

```
python3 -m pytest tests/ -q
```

18 tests, all passing. They cover field mapping, Fahrenheit conversion,
timestamp parsing, excursion/duplicate/unknown-shipment quarantine,
idempotent warehouse loads, late-data alerts, replay-window filtering,
deterministic feeds, and the end-to-end run.

## Layout

```
cold_chain/
  models.py      shared Shipment / TelemetryReading / Milestone models
  sources.py     source adapters + deterministic synthetic feeds
  normalize.py   config-driven mapping into the shared models
  quality.py     validation checks, quarantine, excursion alerts
  monitor.py     run summaries, late-data alerts, warehouse, replay
configs/partners.json   partner field maps and units
run_pipeline.py         end-to-end run
tests/                  pytest suite
```

## Skills shown

Python, SQL-style data modeling, ETL/ELT (batch and incremental),
schema mapping, data-quality checks, pipeline monitoring and alerting,
replay/backfill, JSON/CSV ingestion, deterministic testing with pytest.
