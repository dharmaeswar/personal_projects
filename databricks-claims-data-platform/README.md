# Databricks Claims Data Platform

A portfolio project for a Data Engineer role (Databricks / Spark / Azure).
It builds the pipeline the JD asks for over synthetic healthcare member and
claims data: ingest raw feeds, cleanse and transform them through a
bronze → silver → gold lakehouse, enforce data-quality checks with
quarantine, publish reconciled gold aggregates, and expose the large
datasets to applications through a paginated read API — orchestrated as an
ADF-style pipeline and provisioned with Terraform.

**All data is synthetic and seeded (seed 42).** No real member, patient,
claim, or PHI data is used, and nothing here is a claim about any real
insurer or person.

## Runs locally, without a Spark cluster or an Azure subscription

Databricks, Spark, and Azure are not installed here, so the pipeline runs
locally with pandas + Parquet and the API with the Python standard library.
It does **not** pretend a cluster or cloud run happened. Every pandas
operation names the Spark operation it mirrors, so the same code maps
one-to-one onto a real Databricks job; the Terraform in `infra/` is
plan-only and provisions nothing. `requirements.txt` lists only pandas,
pyarrow, numpy, pytest.

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

## Results (real run, Nov 26, 2026)

```
raw=324 duplicates=4 quarantined=24 cleansed=296 gold_daily=194 total_paid=$1,079,949.49
checks: 7/7 passed, reconciliation=PASS
```

- Raw rows: **324** (300 clean + 24 planted defects)
- Duplicates removed by window dedup: **4**
- Quarantined rows: **24** — paid_amount_mismatch 9, null_member_id 5, negative_paid_amount 4, service_date_out_of_range 3, unknown_diag_code 3
- Cleansed rows: **296**; total cleansed paid **$1,079,949.49**
- Gold daily rows: **194** (daily paid by service date / plan); gold monthly rows: **60**
- Quality checks: **7/7 PASS** (schema, dedup, completeness, non-negative paid, diag codes, arithmetic, reconciliation)

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
python run_pipeline.py            # bronze -> silver -> gold + validation report
python run_orchestrated.py        # same load through the ADF-style DAG runner
python run_api.py 8080            # serve the read API on port 8080
python -m pytest -q               # 24 tests
```

`run_pipeline.py` writes Parquet + CSV tables under `lakehouse/` (bronze,
silver, quarantine, gold/daily partitioned by `service_date`,
gold/monthly) and a human-readable `validation_report.txt` in the project
root. `terraform plan` in `infra/` reviews the Azure resources (nothing is
applied; the Synapse SQL password is passed via `TF_VAR_synapse_sql_password`,
never committed).
