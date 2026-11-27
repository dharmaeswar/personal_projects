# Product Analytics ELT Orchestration

A portfolio project for a **Software Engineer II, Data Analytics & Engineering** role (Pinterest-style). It builds the data foundation product and data-science teams need for trusted, self-service analytics: raw product events become partitioned analytics tables, window-function metrics and a generated dataset catalog, all driven by a small DAG orchestrator.

**All data is synthetic and seeded.** No real user, pin, or product data is used, and nothing here is a claim about any real company.

## Problem statement

Product teams need fast, consistent answers — daily actives, retention, funnels, session behaviour — but raw product events are messy: producers ship events that break the agreed schema, batches get re-delivered, late events arrive, and every team defines "retention" slightly differently. Ad-hoc queries against the raw stream are slow and disagree with each other.

This project fixes that with an analytics-engineering pipeline:

- **Instrumentation contracts** — every event type has a schema (required fields plus required nested payload keys). Contract breaks are quarantined with the reason, never silently loaded.
- **ELT with partitioning** — raw events are staged, deduplicated on `event_id`, and fanned out into per-day partition tables (`events_YYYYMMDD`) with per-partition indexes, so a one-day query reads one small table.
- **Window-function metrics** — sessionization with `LAG()` and a 30-minute gap, 7-day retention cohorts, and an ordered view → save → click funnel, all in plain SQL.
- **Metric definitions as code** — `configs/metrics.yaml` is the single source of truth; dashboards and ad-hoc queries read the same definition.
- **DAG orchestration** — tasks with dependencies (`validate_and_load → build_staging → build_sessions → compute_metrics → experiment_checks → quality_checks → publish_catalog`), topological ordering, one retry per failed task, downstream tasks skipped on failure, every attempt recorded in `run_state`.
- **Data quality + discoverability** — completeness, uniqueness, timestamp and freshness checks written to `quality_results`; the publish step regenerates `CATALOG.md` from the warehouse that actually ran.
- **Experimentation guardrails** — deterministic hash assignment to the `save_button_variant` test, a chi-square sample-ratio-mismatch check against the intended 50/50 split, a pre-period balance check on the save rate (the arms must match before the test starts), and a post-period lift readout with a two-proportion z-test and 95% confidence interval. A failed guardrail stops the DAG before publish, so no readout ships on a broken experiment.

## Layout

```
product_analytics/
  contracts.py      instrumentation schema validation
  db.py             SQLite schema, partitions, union view
  ingest.py         contract-checked load, dedupe, staging
  transforms.py     sessions / retention / funnel (window functions)
  metrics.py        metric definitions as code + compute
  experiments.py    A/B assignment, SRM, balance and lift guardrails
  orchestration.py  DAG runner: order, retry, run state
  quality.py        data-quality checks
  catalog.py        generated dataset catalog
  optimize.py       partition pruning vs full scan (EXPLAIN QUERY PLAN)
  seed.py           deterministic synthetic events
run_pipeline.py     end-to-end run: seed -> DAG -> report
configs/            instrumentation.yaml, metrics.yaml
tests/              pytest suite (contracts, ingest, transforms,
                    metrics, experiments, orchestration, quality/catalog/optimize)
```

## Discord update — dbt-style modeling layer (Nov 27, 2026)

Built for a Data Engineer role (Gaming / Ads squads) whose core work is
curated, tested, documented datasets in BigQuery using dbt. New in this update:

- **dbt-style models** (`models/`, `product_analytics/models.py`) —
  staging → intermediate → mart SQL models, wired with `{{ ref() }}`, run in
  the order declared in `models/schema.yml`. `build_models` is a DAG task
  between `quality_checks` and `publish_catalog`.
- **Squad marts** — Gaming: `mart_gaming_daily` (daily active gamers,
  sessions, play minutes by game, from a third-party-style game catalog
  joined to user-to-game play sessions). Ads: `mart_ads_measurement_daily`
  (impressions, clicks, spend, CTR, CPC by campaign and channel).
- **Schema tests as code** — `models/schema.yml` declares unique, not_null,
  relationships, accepted_values and non_negative tests plus a freshness
  check; every build enforces them, writes `model_test_results`, and fails
  the DAG on a failure. Docs regenerate into `MODELS.md` from the warehouse
  that actually ran.
- **Semantic layer** (`configs/semantic_layer.yaml`) — shared metric
  definitions (gaming DAU, play minutes, ads CTR/CPC/spend) naming the mart
  they are defined on; the build validates that each metric's model and
  columns exist, and each metric evaluates to a non-null value on its mart.
- **Honest scope:** the models run locally on SQLite; the SQL is standard
  SQL except the `event_date` extraction in `stg_events`
  (`substr(event_ts, 1, 10)` here, `DATE()` on BigQuery). This is a
  dbt-style modeling layer, not a live dbt + BigQuery deployment — no live
  dbt run or BigQuery warehouse is claimed. All game, ad and session data
  is synthetic and seeded deterministically (`seed_squad_sources`).

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py
python -m pytest -q
```

`run_pipeline.py` seeds 6,000 synthetic events over 14 days, runs the DAG, prints DAU and the funnel for the latest day, and writes `CATALOG.md`. The seed includes deliberately broken rows (missing user, duplicate id, unknown type, missing payload key) so the contract and quarantine paths run on every execution. The `build_models` step also prints all 20 schema-test results and writes `MODELS.md` (7 models: 56 gaming-mart rows and 56 ads-mart rows over 7 days).

## Query optimization — what partitioning buys

`product_analytics.optimize.compare(conn, "2026-11-03")` runs the same one-day distinct-users query against the full staged table and against that day's partition, and returns both `EXPLAIN QUERY PLAN` outputs. The partitioned query reads only `events_20261103` (plus its index); the full-table query scans all staged history. Both return the same count — partitioning changes the plan, not the answer.

## Design notes

- SQLite stands in for the warehouse; every transform is standard SQL window functions, so the same queries run unchanged on BigQuery, Snowflake or Spark SQL.
- Deduplication is "first occurrence wins" on `event_id`, which makes re-delivered batches idempotent.
- Quality failures block the publish step in the DAG: bad data never reaches the catalog.
- The orchestrator is intentionally small — the behaviour that matters (dependency order, retry once, skip downstream, record attempts) is what is tested.
