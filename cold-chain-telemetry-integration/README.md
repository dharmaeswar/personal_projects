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
- **Partner onboarding** (`cold_chain/onboarding.py`) — before a partner
  goes live, their spec is validated against the shared models (every
  required field mapped, temperature unit known) and their sample data is
  dry-run through the normalizer without loading anything. The launch
  readiness report says go or no-go with the exact reasons, so a bad spec
  never reaches production.

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

41 tests, all passing. They cover field mapping, Fahrenheit conversion,
timestamp parsing, excursion/duplicate/unknown-shipment quarantine,
idempotent warehouse loads, late-data alerts, replay-window filtering,
deterministic feeds, the end-to-end run, and partner onboarding (spec
validation, sample dry runs, launch readiness).

## Layout

```
cold_chain/
  models.py      shared Shipment / TelemetryReading / Milestone models
  sources.py     source adapters + deterministic synthetic feeds
  normalize.py   config-driven mapping into the shared models
  quality.py     validation checks, quarantine, excursion alerts
  monitor.py     run summaries, late-data alerts, warehouse, replay
  onboarding.py  partner spec validation, sample dry run, launch readiness
configs/partners.json   partner field maps and units
run_pipeline.py         end-to-end run
tests/                  pytest suite
```

## Skills shown

Python, SQL-style data modeling, ETL/ELT (batch and incremental),
schema mapping, data-quality checks, pipeline monitoring and alerting,
replay/backfill, JSON/CSV ingestion, deterministic testing with pytest.

## Operational AI — customer-defined detections and agentic workflows

`cold_chain/operational_ai.py` builds on the normalised telemetry above,
for the Operational AI use case: turning sensor streams into tools that
help operators understand everyday work.

- **Customer-defined detection rules** — a customer writes their own
  rules (field, operator, threshold, severity, recommended action), for
  example "temperature above 8 C means a door left open". The engine
  runs every rule over every reading and raises one detection per hit.
- **Detection-quality scoring** — detections are scored against
  human-labelled events (precision, recall, F1 by reading id), so
  detection quality and customer impact guide the next rule revision.
- **Agentic workflow** — a detection proposes its rule's recommended
  action; the outcome (what was done, whether it resolved) is recorded,
  and the resolution rate is the feedback loop. The agent never changes
  a detection on its own.
- **Latency and compute-cost tracking** — every detection carries its
  evaluation latency and cost, so reliability, response time and cost
  stay visible as usage grows.

## Operational AI demo (seed 7, deterministic)

```
python3 -m cold_chain.operational_ai
```

| Measure | Value |
|---|---|
| Readings | 48 |
| Detections | 15 |
| Precision / Recall / F1 | 0.8 / 1.0 / 0.8889 |
| True positives / false positives / false negatives | 12 / 3 / 0 |
| Workflow resolution rate | 0.4 |
| Total latency / avg latency | 22.5 ms / 1.5 ms |
| Total compute cost | $0.0302 |
