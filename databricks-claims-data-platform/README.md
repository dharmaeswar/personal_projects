# Databricks Claims Data Platform

A portfolio project for a Data Engineer role (Databricks / Spark / Azure).
It builds the pipeline the JD asks for over synthetic healthcare member and
claims data: ingest raw feeds, cleanse and transform them through a
bronze → silver → gold lakehouse, enforce data-quality checks with
quarantine, publish reconciled gold aggregates, score every cleansed claim
with a paid-amount ML model that flags unusual claims for human review, and
expose the large datasets to applications through a paginated read API —
orchestrated as an ADF-style pipeline and provisioned with Terraform.

**All data is synthetic and seeded (seed 42).** No real member, patient,
claim, or PHI data is used, and nothing here is a claim about any real
insurer or person.

## Runs locally, without a Spark cluster or an Azure subscription

Databricks, Spark, and Azure are not installed here, so the pipeline runs
locally with pandas + Parquet and the API with the Python standard library.
It does **not** pretend a cluster or cloud run happened. Every pandas
operation names the Spark operation it mirrors, so the same code maps
one-to-one onto a real Databricks job; the Terraform in `infra/` is
plan-only and provisions nothing. `requirements.txt` lists pandas,
pyarrow, numpy, scikit-learn, pytest.

## Spark / Databricks mapping

| This project (pandas) | Databricks / Spark equivalent |
|---|---|
| `dedupe_latest` — sort + drop duplicates | `ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY ingested_at DESC)` + filter `rn = 1` |
| `join_member_dim` merge | broadcast join against the 120-row member dimension |
| `filter_valid` boolean rules + quarantine | `WHERE` with the same rules; rejected rows to a quarantine Delta table with a reason column |
| `with_derived_columns` | `withColumn("paid_band", ...)` |
| `aggregate_daily` groupBy | `GROUP BY service_date, plan` with `sum(paid_amount)`, `count(*)` |
| `aggregate_monthly` groupBy | `GROUP BY service_month, plan, diag_group` |
| Partitioned Parquet write | `df.write.partitionBy("service_date").parquet(...)` into ADLS Gen2 (bronze / silver / gold) |
| Schema enforcement | `StructType` validation before any write lands |
| `ml.py` — paid-amount model + scoring | Spark ML Pipeline: `VectorAssembler` + `StandardScaler` + `OneHotEncoder` + `LinearRegression`, batch-scored in a Databricks notebook step writing a Delta table (`gold/model_scores`) |

## Azure mapping

| This project | Azure equivalent |
|---|---|
| `lakehouse/bronze|silver|gold` folders | ADLS Gen2 containers of the same names |
| `pipelines/claims_daily.json` + DAG runner | Azure Data Factory pipeline (Copy + Databricks Notebook + Web activities, retry policy) |
| `claims_platform/api.py` | The API that exposes gold datasets to applications and analytics solutions |
| `infra/main.tf` | Terraform for resource group, ADLS Gen2, Data Factory, Synapse workspace, Databricks workspace |

## What it validates

- **Schema**: column presence and dtypes enforced on the silver layer before it is written.
- **Dedup**: window-function rule keeps the latest copy of each `claim_id`.
- **Completeness**: null `member_id` quarantined.
- **Ranges**: negative paid amounts, service dates outside 2026-09-01 – 2026-11-15.
- **Referential integrity**: `diag_code` must be a known code; `member_id` must exist in the member dimension.
- **Arithmetic**: `paid_amount` must equal `billed_amount - adjustment` (within 0.01).
- **Reconciliation**: gold daily paid must equal silver paid grouped the same way (max diff 0.0).

One honest wrinkle the checks caught: the 4 late duplicate copies carry
`paid_amount` $1.00 higher than the original, so after dedup keeps the
latest copy, those 4 rows fail the arithmetic check and land in quarantine
as `paid_amount_mismatch` (9 total: 5 planted + 4 duplicates). A late
correction that changes a value is a real data-quality break, and the
pipeline treats it as one instead of silently keeping it.

## AI / ML scoring (added Nov 27, 2026)

After the gold publish, the ADF pipeline runs a `ScoreClaimsML` Databricks
notebook step (`claims_platform/ml.py`): a Ridge regression predicts
`paid_amount` from `billed_amount`, service month, plan, diagnosis group,
and age band — deliberately **not** from `adjustment`, so the residual
measures whether a claim's paid amount looks unusual for its billed amount
and cohort. Each scored claim lands in `gold/model_scores` with its
predicted paid, residual, residual z-score, and a `model_flag`
(`high_residual` when |z| >= 3).

**Model card / responsible AI:** the model is trained and scored on the
same synthetic, seeded data (seed 42) — no PHI, no real members or claims.
It is a review queue, not a decision: a flagged claim goes to a human
reviewer; the model never auto-denies, auto-pays, or otherwise decides a
claim. On this seeded run the model scores all 296 cleansed claims and
flags **0** for review — the clean synthetic data has no extreme paid
outliers — while `tests/test_ml.py` proves the flag works by planting a
claim paid at 5x its billed amount and asserting it is flagged.

## Results (real run, Nov 27, 2026)

```
raw=324 duplicates=4 quarantined=24 cleansed=296 gold_daily=194 total_paid=$1,079,949.49
checks: 8/8 passed, reconciliation=PASS
ML: test MAE=$230.87 R2=0.9771 flagged_for_review=0
```

- Raw rows: **324** (300 clean + 24 planted defects)
- Duplicates removed by window dedup: **4**
- Quarantined rows: **24** — paid_amount_mismatch 9, null_member_id 5, negative_paid_amount 4, service_date_out_of_range 3, unknown_diag_code 3
- Cleansed rows: **296**; total cleansed paid **$1,079,949.49**
- Gold daily rows: **194** (daily paid by service date / plan); gold monthly rows: **60**
- ML scores: **296** rows in `gold/model_scores`; test MAE **$230.87**, test R² **0.9771**, **0** flagged for review
- Quality checks: **8/8 PASS** (schema, dedup, completeness, non-negative paid, diag codes, arithmetic, reconciliation, ml_scoring)

## Streaming: Autoloader + Delta Live Tables + watermark (added Nov 27, 2026)

`claims_platform/streaming.py` adds the incremental side of the same lakehouse, for a
Senior Databricks Data Engineer role: `split_into_batches` mirrors Autoloader
(cloudFiles) incremental discovery in arrival order; `apply_expectations` mirrors DLT
`expect_or_drop` on the five data-quality rules and `expect_or_fail` on
`claim_id_present` (a failed batch lands zero rows and is recorded for reprocessing);
`apply_watermark` mirrors Structured Streaming `withWatermark` on `service_date`
(event time); `merge_upsert` mirrors Delta `MERGE INTO` silver keyed on `claim_id`,
latest `ingested_at` wins. `pipelines/claims_streaming_job.json` is the Databricks
Workflows job (Autoloader ingest → DLT pipeline → gold aggregates + ML scoring →
quality gate), and `pipelines/claims_dlt.json` is the DLT pipeline definition with
the same expectations. Unity Catalog target is catalog `claims`, schemas
bronze/silver/gold; `member_id` is treated as governed data (access by grant, no
raw member identifiers in published gold tables — gold carries plan-level aggregates
only). As with the batch path, everything runs locally with pandas; no cluster,
workspace, or cloud run is claimed.

Seeded streaming run (`python run_streaming.py`, Nov 27, 2026): 324 raw rows in 13
micro-batches (size 25) → **300 silver rows** (300 unique claim_ids, reconciliation
PASS), 24 dropped (paid_amount_arithmetic 9, valid_member_id 5, non_negative_paid 4,
service_date_in_range 3, known_diag_code 3), 0 failed batches, 0 late rows at the
120-day watermark, total silver paid **$1,094,167.31**. One honest difference from
the batch run (296 cleansed): the batch path dedups first and keeps the +$1.00
duplicate copy, which then fails the arithmetic check and is quarantined — losing
those 4 claims. The streaming path checks expectations first, so the bad copy is
quarantined and the good original lands; silver keeps all 300 clean claims.

## The API layer

`claims_platform/api.py` (stdlib-only, no framework) exposes the large
datasets with pagination — never one unbounded dump (default limit 50,
max 500):

```
GET /health
GET /claims?plan=Medicaid&diag_group=Cardiology&limit=50&offset=0
GET /claims/C00001
GET /members/M0001
GET /gold/daily?service_date=2026-10-05
GET /gold/monthly?service_month=2026-10
```

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py            # bronze -> silver -> gold + ML scores + validation report
python run_streaming.py           # Autoloader-style micro-batches -> DLT expectations -> silver_streaming
python run_orchestrated.py        # same load through the ADF-style DAG runner
python run_api.py 8080            # serve the read API on port 8080
python -m pytest -q               # 45 tests
```

Or use the automation scripts (PowerShell + Bash — same steps, tests first):

```powershell
powershell -File scripts/run_pipeline.ps1
```

```bash
bash scripts/run_pipeline.sh
```

`run_pipeline.py` writes Parquet + CSV tables under `lakehouse/` (bronze,
silver, quarantine, gold/daily partitioned by `service_date`,
gold/monthly, gold/model_scores) and a human-readable `validation_report.txt` in the project
root. `terraform plan` in `infra/` reviews the Azure resources (nothing is
applied; the Synapse SQL password is passed via `TF_VAR_synapse_sql_password`,
never committed).
