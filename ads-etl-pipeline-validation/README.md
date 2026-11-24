# Advertising ETL Pipeline Validation

A portfolio project for a Data Engineer role in advertising (Amazon
Advertising Demand Enablement & Product Ops style). It builds a small
bronze → silver → gold pipeline over synthetic ad impression / click /
spend events and validates every layer the way a data-quality team
would: schema enforcement, completeness, uniqueness, ranges,
referential integrity, spend arithmetic, late-arriving data handling,
and reconciliation of gold aggregates back to silver.

**All data is synthetic and seeded.** No real advertiser, campaign, or
spend data is used, and nothing here is a claim about any real company.

## What it does

- **Streaming-style ingest** — an in-memory event consumer delivers
  bronze events in batches with offsets and commits, so an
  uncommitted batch is re-delivered (at-least-once delivery). No broker
  or streaming library is involved; the consumer models the
  produce / poll / commit pattern in plain Python.
- **Bronze** — raw ingest into SQLite, append-only in spirit. Nothing
  is cleaned here, so bad source rows are visible.
- **Silver** — cleaned, deduplicated, type-checked events. Bad rows are
  moved to a quarantine table with the reason they failed instead of
  being dropped silently. Late-arriving rows (dated before the
  2026-10-01 watermark) are valid data: they land in silver flagged
  `late_arriving = 1` and are counted, not quarantined.
- **Gold** — daily spend, impressions, and clicks by campaign and
  channel, built from silver with a real SQL `GROUP BY` query
  (`sqlite3`, standard library only).
- **Lineage** — every silver row maps to its bronze `event_id`, and
  every gold group lists the silver `event_id` values that fed it
  (see `lineage.json`).
- **Transaction log** — every table write appends a versioned entry to
  `ads_tables/pipeline_log.json` (version, operation, rows added,
  rows removed).
- **Monitoring** — per-stage row counts and timings, failure rate,
  late-arrival rate, and throughput, printed in the report.

## What it validates

- **Schema**: column presence, types, nullability per table.
- **Completeness**: nulls in key columns.
- **Uniqueness**: duplicate `event_id` values.
- **Ranges**: impressions >= 0, clicks >= 0, spend >= 0,
  `event_ts` inside 2026-09-01 … 2026-11-16.
- **Consistency**: clicks must not exceed impressions.
- **Referential integrity**: every event's `ad_id` and `campaign_id`
  must exist in the dimension tables.
- **Arithmetic**: `spend_usd` must equal `clicks * cpc_usd` (within 0.01).
- **Reconciliation**: gold daily spend must equal silver spend grouped
  the same way (within 0.01).

The bronze fixture plants 14 bad rows on purpose (3 duplicate
event_ids, 3 null campaign_ids, 2 negative spends, 2 rows with clicks
above impressions, 2 unknown ad_ids, 1 future event date, 1 wrong
spend). The pipeline must quarantine all 14, and the report must list
each violation type with its count. Two further rows are late-arriving
(September dates): they stay in silver, flagged.

## Results of a run

```
Bronze events: 254 rows
Silver events: 240 rows
Quarantined rows: 14 rows
Late-arriving rows in silver: 2 rows
Gold daily campaign groups: 193
Silver total spend: $47,910.22
Gold total spend:   $47,910.22
Bronze checks: 3 of 10 passed, 7 FAILED (as designed — the planted rows)
Reconciliation: PASS — gold matches silver on all 193 daily campaign groups
Failure rate: 5.51% (14 of 254 bronze rows quarantined)
Late-arrival rate: 0.83% (2 of 240 silver rows late)
```

## Data contracts and the data-ops agent (added Nov 24, 2026)

- **Data contracts** (`ads_etl/contracts.py`) — a versioned contract for
  each table (bronze, silver, gold): exact columns, types, nullability,
  value ranges, and the owning team. `validate_contract` checks rows
  against the contract before a write is accepted; `detect_drift`
  reports added/removed columns and type changes against the contract on
  file. The seeded run holds on silver and gold; the bronze contract
  flags the 2 planted rows that break it (a null key and a negative
  spend), which is the contract doing its job.
- **Data-ops agent** (`ads_etl/agent.py`, run with `python run_agent.py`)
  — a deterministic, rule-based simulation of the agentic pattern used
  to automate the data operations lifecycle: three specialist agents
  (ingest, quality, governance) call tools (`run_quality_checks`,
  `check_contract`, `inspect_quarantine`, `lookup_lineage`,
  `plan_backfill`), and an orchestrator turns their findings into one
  action plan where every action names its evidence. There is no LLM
  call: the agent is fully reproducible and auditable by design. On the
  seeded run it plans 4 actions — 2 blocks (7 failed bronze checks, 2
  bronze contract violations), 1 fix (top quarantine cause: duplicate
  event_id, 3 rows), 1 watch (2 late-arriving rows in silver) — and
  writes `agent_report.json` and `agent_report.txt`.

## How to run

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python run_pipeline.py
python run_agent.py
python -m pytest -q
```

`run_pipeline.py` writes the SQLite database to
`ads_tables/ads_etl.db`, the transaction log to
`ads_tables/pipeline_log.json`, `lineage.json`, and a human-readable
`validation_report.txt` in the project root.

## Layout

```
ads_etl/
  data.py        synthetic campaigns, ads, events (seeded) + planted violations
  schema.py      expected schemas + enforcement
  checks.py      data-quality checks (each returns pass/fail + failing rows)
  contracts.py   versioned data contracts + drift detection
  agent.py       deterministic data-ops agent (tools, agents, orchestrator)
  streaming.py   in-memory event consumer (offsets, batches, commit/replay)
  pipeline.py    bronze -> silver -> gold in SQLite, lineage, transaction log
  monitoring.py  per-stage timings, failure/late rates, throughput
  report.py      renders validation_report.txt
run_pipeline.py  runner
run_agent.py     runner: pipeline + data-ops agent, writes agent_report.*
tests/           46 pytest tests
```

## Honest limits

- The data is synthetic and small (254 events); nothing here proves
  performance at advertising scale.
- The "streaming" consumer is in-memory and single-process: it shows
  offset/commit/replay logic, not a real distributed stream.
- Gold is built with SQLite, not a distributed engine; the SQL
  patterns (joins, `GROUP BY`, window-free aggregation) transfer, but
  the engine does not.
- Checks run on the full bronze batch in Python; a production pipeline
  would run them incrementally and alert on failure-rate thresholds
  instead of only reporting them.
- The data-ops agent is a deterministic simulation of agentic patterns
  (tool use, planning, multi-agent orchestration) with explicit rules
  and no model call; it demonstrates the workflow and its audit trail,
  not a live LLM agent.
