# Home Health Snowflake Warehouse

A portfolio project for the **Humana — Data Engineer II, Home Health (R-434927)**
application. It builds the data warehouse the posting describes: home-health
visit feeds and referral/order records from an integration API are ingested,
validated, and loaded into a Snowflake-style warehouse — a star schema with
SCD Type 2 history, watermark-based incremental loads, data-quality checks
with quarantine, PHI governance, and reconciliation of every load.

**All data is synthetic and seeded.** No real patient, clinician, visit, or
Humana data is used, and nothing here describes a real Humana system. The
warehouse runs locally on SQLite as a stand-in for Snowflake; the production
SQL scripts in `homehealth/sql/` are Snowflake SQL and are validated
structurally by the test suite. The Databricks-style patterns (bronze →
silver → gold, Delta-style transaction log) are named as their equivalents in
the code.

## Problem statement

Home-health operations need trusted answers — "which patients were visited,
by whom, for how long, and did the visit match the referral?" — but the
sources disagree: visit feeds arrive as CSV from field devices, referrals
arrive as paginated JSON from an integration API (the MuleSoft-style layer),
care plans change mid-episode, and a bad row loaded into the warehouse
becomes a wrong report for care teams. This project fixes that with a
validated pipeline:

- **Ingest** (`homehealth/ingest.py`) — a CSV visit-feed parser and a
  paginated JSON referral API client with retry on transient failures. Every
  record is tagged with source + schema version; malformed rows are reported,
  never silently dropped.
- **Validate** (`homehealth/quality.py`) — six rules: visit date present and
  not in the future, duration in 5–480 minutes, clinician id present,
  patient key present, no duplicate visit id, assessment score in 0–100.
  Every failure is quarantined with the rule that caught it; nothing invalid
  reaches the warehouse.
- **Model** (`homehealth/warehouse.py`) — star schema: `dim_patient` (SCD
  Type 2 on care plan), `dim_clinician`, `dim_date`, and
  `fact_home_visit` grained at one visit per patient per clinician per day,
  with a UNIQUE natural key so re-runs are idempotent. Incremental loads use
  a watermark; a full-refresh mode rebuilds from scratch. Every load writes a
  load-log row and a reconciliation report (source rows vs loaded vs
  quarantined).
- **Govern** (`homehealth/governance.py`) — PHI handling: patient names are
  hashed before they reach reporting tables, the audit log records every
  load and every quarantine decision, and a role check gates who may read
  identifiable fields.
- **Orchestrate** (`homehealth/pipeline.py`) — a small DAG runner
  (ingest → validate → load → reconcile → publish) with topological order,
  one retry per failed task, and run state in the warehouse so a failed run
  resumes instead of re-loading.
- **Snowflake SQL** (`homehealth/sql/`) — the production scripts: warehouse
  tables, a `MERGE`-based load, and the reconciliation query. They are
  Snowflake SQL and are checked structurally by the test suite; the runnable
  pipeline mirrors their logic on SQLite so the behaviour is testable
  without a Snowflake account.
- **CI/CD** (`azure-pipelines.yml`) — the Azure DevOps pipeline definition
  (test → lint → package) the team would run on every push.

## Layout

```
homehealth/
  ingest.py       CSV visit feed + paginated referral API client (retry)
  quality.py      six validation rules + quarantine
  warehouse.py    star schema, SCD2 patient dim, watermark loads, reconcile
  governance.py   PHI hashing, audit log, role check
  pipeline.py     DAG orchestration, retries, run state
  sql/
    01_create_tables.sql   Snowflake DDL
    02_load_visits.sql     Snowflake MERGE load
    03_reconcile.sql       Snowflake reconciliation query
data/
  visits.csv      16 seeded visits (12 valid, 4 quarantined)
  referrals.json  6 seeded referrals (paginated API fixture)
tests/
  test_ingest.py  test_quality.py  test_warehouse.py
  test_governance.py  test_pipeline.py  test_sql.py
run_pipeline.py   CLI; writes visit_report.json + CATALOG.md
azure-pipelines.yml
```

## Run it

```bash
python -m pytest -q            # 31 tests
python run_pipeline.py         # demo run: 16 visits -> 12 loaded, 4 quarantined
```

Demo run: 16 raw visits → 12 loaded, 4 quarantined (1 duplicate visit id,
1 negative duration, 1 missing clinician, 1 future visit date); the referral
API retried once on an injected transient failure; reconciliation matches
(16 source = 12 loaded + 4 quarantined); re-run inserts 0 rows (idempotent);
patient names in the reporting view are SHA-256 hashes, never plain text.

## Honest limits

All data is synthetic and seeded; nothing describes real Humana, CenterWell,
patient, or visit data. The referral API is simulated in-process, not a real
MuleSoft flow or HTTP service — MuleSoft itself is not claimed as a skill.
The warehouse is SQLite, not Snowflake; the Snowflake SQL is validated
structurally, not executed against Snowflake. Azure Databricks / Azure
Storage / Azure DevOps are demonstrated as patterns (medallion layers,
Delta-style log, pipeline YAML), not run on Azure. Demonstrated on 16 seeded
visits, not at production scale. Not implemented: real-time streaming, a live
Snowflake account, HIPAA certification, or production PHI access controls.
