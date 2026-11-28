# Regulated Savings Data Platform

A portfolio project for a **Senior Database Engineer / Data Engineer** role
(BNY, Project Crawford data platform, Job 83175). It builds the governed
data platform the JD asks for over synthetic data for a regulated long-term
savings program: batch contribution files and Kafka-style event streams are
ingested into a bronze → silver → gold lakehouse, with data-quality checks
and quarantine, lineage and an append-only audit log, reconciliation of
every gold balance back to silver, observability with alerting, and an
anomaly-detection feed for the applied-AI review queue — all under
role-based access and a FedRAMP/NIST-style control checklist.

**All data is synthetic and seeded (seed 42).** No real account holder,
child, or program data is used, and nothing here is a claim about any real
institution or government program.

## Runs locally, without a Spark cluster, Kafka, Databricks, or Azure

Spark, Kafka, Databricks, Snowflake, and Azure are not installed here, so
the pipeline runs locally with pandas + Parquet and the event stream as a
local event log. It does **not** pretend a cluster, broker, or cloud run
happened. Every pandas operation names the Spark / Databricks operation it
mirrors, so the same code maps one-to-one onto a real PySpark / Databricks
job — swap the DataFrame calls for Spark equivalents and the logic is
unchanged. `requirements.txt` lists only pandas, pyarrow, numpy, pytest.

## Spark / Databricks / Kafka mapping

| This project (pandas) | Production equivalent |
|---|---|
| `dedupe_latest` — sort + drop duplicates | `ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ingested_at DESC)` + filter `rn = 1` (re-delivery safe) |
| `validate_contributions` — rule checks, quarantine table | Spark `WHERE` checks; bad rows to a Delta quarantine table with a reason |
| Bronze → silver → gold Parquet writes + `_delta_log.json` | Databricks Delta Lake medallion tables with transaction log |
| `scd2_status_history` — open/closed status rows | Delta `MERGE` on account_id (Type-2 slowly changing dimension) |
| `build_gold` — `groupby` sums, monthly/program aggregates | Spark `GROUP BY` gold aggregates built only from silver |
| `reconcile_balances` — gold vs silver recompute | Reconciliation job: gold balance must equal silver contributions − disbursements + investments, to the cent |
| `build_lineage` — silver row → source event id | Unity Catalog-style lineage registry |
| `run_streaming.py` — two micro-batches over the event log | Spark Structured Streaming micro-batch consumer on a Kafka topic |
| `flag_anomalies` — per-account z-score + median rule | Feature/monitoring pattern an ML anomaly model consumes |
| `check_access` / `control_checklist` | Role-based access (Unity Catalog) + FedRAMP/NIST control checks |

## What it validates

- **Ingest:** 917 raw rows (600 batch contributions + 300 stream events +
  17 re-deliveries) → 900 deduped → 805 silver, 42 quarantined (4.6%):
  negative amounts, unknown accounts, missing dates — each with a reason.
- **Gold:** 120 account balances, total $1,769,680.58; monthly and
  program-level contribution aggregates built only from silver.
- **Reconciliation:** 120/120 accounts reconcile to the cent — 0 breaks.
- **Streaming:** 305 events in 2 micro-batches → 241 silver rows, 6
  quarantined; re-deliveries deduped across batches.
- **Anomaly detection:** 1 of 743 contributions flagged for review
  (z-score / median rule).
- **Governance:** PII (`holder_id`) blocked for analyst role, open to
  auditor/data-engineer; 5/5 controls satisfied; append-only audit log.

## Run it

```bash
python -m pytest -q            # 22 tests
python run_pipeline.py         # batch: bronze -> silver -> gold, report
python run_streaming.py        # Kafka-style micro-batch consumption
python run_anomaly.py          # anomaly flags + governance checks
```

Outputs: `tables/*.parquet` + `_delta_log.json`, `audit_log.jsonl`,
`run_report.json`, `streaming_report.json`, `anomaly_report.json`,
`governance_report.json`.

## Honest limits (also stated in the resume package notes)

pandas + Parquet stand in for Spark/Databricks; a local event log stands in
for Kafka; SQLite is not used here and no live Snowflake, Databricks,
Azure, or Kafka service is involved. The resume does NOT claim production
Spark, Kafka, Databricks, Snowflake, or Scala experience beyond what
Dharma's record supports — the project demonstrates the patterns, and the
match table in the application package marks Scala, Snowflake, and
FedRAMP/NIST production experience as gaps.
