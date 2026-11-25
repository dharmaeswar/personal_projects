# Forward-Deployed Governed Data Integration for AI Systems

A portfolio project for EY's **Advanced Forward Engineering (AFE) — Data
Engineer, Senior** role: the data-owner toolkit for a delivery pod that
deploys AI-native systems into highly regulated client environments
(tax, finance, risk).

**All data is synthetic and seeded in code.** No real EY, client, tax, or
financial data appears anywhere, and nothing here ran in production or at
any real company.

## The problem

A traditional data-engineering role builds one central platform. A
forward-deployed data engineer does the opposite: they sit inside a
delivery pod, embedded with a strategic customer, and make that customer's
messy legacy data accessible, governed, and production-ready so an AI
system can run safely inside a regulated environment. The same pod must
ingest a Postgres dump, an Oracle extract, and a paginated REST API —
each with its own schema version — enforce data contracts, prove lineage
and access control, catch schema drift before it corrupts a model, and
serve retrieval to the AI system without ever handing it raw restricted
data.

## What it does

| Module | AFE responsibility it covers |
|---|---|
| `afe_data/sources.py` | One adapter interface for Postgres CSV dumps, Oracle pipe-delimited extracts, and a paginated REST API (one retry on transient failure). Every row tagged with source + schema version. |
| `afe_data/contracts.py` | Data contracts: expected schema, freshness SLA, completeness floor, allowed (additive) evolution. Breaking changes rejected before load — the DevOps Specification (DS) data requirements for a deployment template. |
| `afe_data/transform.py` | Explicit, versioned field maps onto one canonical model. Handles the v1 → v2 rename (`pos_id` → `position_id`) and reports unmapped columns instead of dropping them silently. Restricted identifiers (e.g. `tax_id`) are deliberately excluded from the canonical AI-facing model. |
| `afe_data/quality.py` | Quality checks (required fields, numeric ranges, duplicate natural keys, referential checks against the client master list) + schema-drift detection. Bad rows go to quarantine with a reason. |
| `afe_data/governance.py` | Column classification (PII patterns + sampled values), masking (redact / last-4 / hash), role + purpose RBAC with an audit log, and an append-only lineage log tracing every published row to its source, schema version, transform, and contract version. |
| `afe_data/retrieval.py` | Governed retrieval for the AI system: TF-IDF ranked search over position documents with citations and per-field sensitivity, plus a point-in-time feature-store snapshot. A deterministic ranker stands in for a live embeddings store (same interface). |
| `afe_data/pipeline.py` | Pod pipeline: ingest → contract → transform → quality → govern → publish into SQLite. Idempotent — a re-run loads zero new rows and appends no duplicate lineage. |

## How to run

```bash
pip install -r requirements.txt   # pytest only
python run_demo.py                # demo: writes afe_demo.db + prints a JSON summary
python -m pytest -q               # tests
```

Requires Python 3.12. The app code uses only the standard library.

## Demo results (real run)

Two legacy feeds plus a reference API:

- Postgres v2 dump (5 rows): 3 loaded, 2 quarantined (1 missing notional,
  1 duplicate natural key). Drift detected: additive `tax_id` column,
  non-blocking; the v1 → v2 rename is handled by the field map.
- Oracle extract (3 rows): 3 loaded.
- REST API (2 pages): 3 reference rows, 1 retry on the injected transient
  failure on page 2.
- 6 positions published, 6 lineage entries, retrieval top hit for
  "IRS swap position ACME" is the matching position document, 6 feature
  rows in the snapshot.

## Honest limits

All data is synthetic and seeded (19 seeded rows across the demo feeds),
not production scale. The warehouse is SQLite, not Postgres / Oracle /
Databricks / Snowflake / BigQuery / RedShift (the patterns are named as
their equivalents in the code). The retrieval ranker is TF-IDF, not live
embeddings; the REST API is simulated in-process, not a real HTTP service;
there is no real Kafka / Flink streaming and no Azure Data Factory
orchestration — the pipeline is a local, deterministic stand-in for those
systems. Not implemented: real Airflow/Databricks jobs, streaming
ingestion, or a production feature store.
