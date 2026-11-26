# Performance Marketing Campaign Platform

A portfolio project for a **Software Data Engineer** role on Disney's
Enterprise Media & Marketing team (Performance Marketing). It builds the
data platform behind the team's campaign planning tools: delivery data
from five ad platforms becomes a campaign plan, a pacing monitor, guarded
in-flight optimisations, and trusted gold tables that data science
workflows read.

**All data is synthetic and seeded (seed 42).** No real campaign,
advertiser, or performance data is used, and nothing here is a claim
about any real company or campaign.

## Runs locally, without Spark, Databricks, Snowflake, or AWS

Spark, Databricks, and AWS are not installed here, so the pipeline runs
locally with pandas + Parquet and the infra builder emits config text.
It does **not** pretend a cluster or cloud run happened. Every pandas
operation names the Spark operation it mirrors, so the same logic maps
one-to-one onto a real PySpark job on Databricks.

## Problem statement

The Performance Marketing team runs paid media across Google Ads, Meta,
DV360, The Trade Desk, and Yahoo. Each platform reports delivery under
different field names; budgets live in campaign plans; optimisations are
applied to live campaigns. Three things go wrong without a platform:

- actuals cannot be compared with the plan, so overspend is found late;
- a bad optimisation (a bid or budget change on a broken signal) reaches
  an in-flight campaign unchecked;
- data science workflows read raw platform feeds that disagree with each
  other.

This project fixes that with one pipeline:

- **Ingest** (`campaign_platform/ingest.py`) — per-platform schema
  contracts; contract breaks quarantined with a reason; native fields
  normalised to one common schema; dedupe on platform/campaign/date.
- **Planning** (`campaign_platform/planning.py`) — the campaign plan:
  total budget spread across the flight into a daily budget, expected
  daily conversions from the target CPA, and budget reallocation across
  platforms by weight.
- **Pacing & safeguards** (`campaign_platform/pacing.py`) — daily pacing
  vs plan (on-track / ahead / behind at ±20%); optimisation guardrails
  HOLD a change on a spend spike (>2x daily budget), zero conversions on
  spend, realised CPA above 1.5x target, or impressions with zero clicks.
  Every HOLD names its reason and requires human review.
- **Quality** (`campaign_platform/quality.py`) — completeness, uniqueness,
  ranges, and referential integrity against the campaign dimension; bad
  rows quarantined with a reason, never dropped silently.
- **Warehouse** (`campaign_platform/warehouse.py`) — bronze / silver /
  gold Parquet medallion; gold is daily aggregates per platform and
  campaign with CTR, CPC, CPA; campaign dimension is SCD Type 2, so a
  budget change closes the old row and opens a new current one.
- **LLM assist** (`campaign_platform/ai_assist.py`) — the team's
  AI/LLM-in-development pattern, done defensibly: a draft summary of
  findings from structured facts, a deterministic evaluator that scores
  it against ground truth (a held campaign must be named), and a human
  gate before anything touches a live campaign. No live LLM is called
  locally; the template stands in for the LLM call with the identical
  input contract and the identical evaluator + gate.
- **Orchestration** (`campaign_platform/orchestration.py`) — Airflow-style
  DAG (ingest → plan/pace + quality → warehouse/summary) with one retry
  per failed task, downstream tasks skipped on failure, every attempt
  recorded.
- **Infra** (`campaign_platform/infra.py`) — Terraform config for the AWS
  footprint (S3 bronze/silver/gold, Glue ingest job, Databricks
  workspace, Snowflake external stage) generated from one environment
  definition; staging and prod differ only by variables.

## How to run

```bash
pip install -r requirements.txt
python run_pipeline.py            # writes output/report.md + report.json
python -m pytest -q               # 25 tests
```

## Results (seeded run — `python run_pipeline.py`)

- 5 campaigns planned across 5 platforms; 70 raw delivery rows ingested,
  0 quarantined at contract, 0 quarantined at quality.
- Medallion: bronze 70 / silver 70 / gold 70 rows (one gold row per
  campaign-day).
- Pacing at day 14: all 5 campaigns on-track.
- Guardrails on the latest day: 5 ALLOW / 0 HOLD (HOLD behaviour is
  covered by the unit tests: spend spike, high CPA, zero clicks).
- Summary draft evaluated clean (score 1.0) with 0 findings, and flagged
  for human review, as every draft is.

## Layout

```
campaign_platform/
  ingest.py         platform contracts, normalisation, dedupe
  planning.py       campaign plan, budget allocation
  pacing.py         pacing vs plan, optimisation guardrails
  quality.py        data-quality checks + quarantine
  warehouse.py      bronze/silver/gold medallion, SCD2 dimension
  ai_assist.py      LLM-assist draft summary + evaluator + human gate
  orchestration.py  Airflow-style DAG with retries
  infra.py          Terraform config generator (AWS/Databricks/Snowflake)
run_pipeline.py     end-to-end run + report
tests/              25 pytest tests
```
