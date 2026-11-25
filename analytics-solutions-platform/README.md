# Analytics Solutions Platform

A portfolio project for Northwestern Mutual's **Analytics & Solutions
Engineer** role (Req JR-46155): an end-to-end analytics data-product
platform that takes messy multi-source data and turns it into governed,
dashboard-ready datasets analysts can trust.

**All data is synthetic and seeded in code.** No real Northwestern
Mutual, customer, or policy data appears anywhere, and nothing here ran
in production or at any real company.

## The problem

Business consumers need answers — "which policies are active, how much
premium do they carry, and how engaged are their holders?" — but the
inputs arrive as a policy extract (CSV), an advisor activity feed
(JSON-lines) and a paginated advisor API, each with its own schema
version, bad rows, and no shared definitions. Raw feeds cannot answer
analytical questions directly: bad rows slip in, the same metric gets
defined two ways in two dashboards, PII leaks into analyst extracts,
and a stale load ships without anyone noticing.

## What it does

| Module | JD responsibility it covers |
|---|---|
| `analytics_solutions/sources.py` | **Acquire** data from CSV, JSON-lines and paginated API sources; every row tagged with source + schema version + ingest time; raw zone written as source/date partitions (the local stand-in for an S3 raw zone) |
| `analytics_solutions/cleanse.py` | **Cleanse + feature engineer**: typed coercion, quarantine with a named reason for every bad row (never silently dropped), dedupe by natural key, tenure / premium-band / recency / rolling 30-day activity features |
| `analytics_solutions/models.py` | **Requirement-driven data models**: dimensional star schema (`dim_holder`, `dim_advisor`, `dim_date`, `fact_policy_activity`) plus the relational staging underneath; stable surrogate keys; foreign keys enforced at load — an orphan fact row fails the load, it is not nulled out |
| `analytics_solutions/metrics.py` | **Governed metrics, one source of truth**: a metric exists only in the registry (name, plain-language definition, formula, owner, grain, source tables); a conflicting redefinition is rejected, so two dashboards can never disagree about what a number means |
| `analytics_solutions/governance.py` | **PII regulations**: rule-based classification (email, phone, SSN, DOB, name, address) by column name + sampled values; masking (redact / last-4 / SHA-256 hash); role-based access — analysts never see restricted columns, engineers see masked values, auditors get a logged read-only view |
| `analytics_solutions/quality.py` | **Testing / data accuracy designs**: completeness, uniqueness, range, referential-integrity and freshness-SLA checks; the gate fails the build when any check fails, so no dataset ships with a failing gate |
| `analytics_solutions/publish.py` | **Publish dashboard-ready datasets**: partitioned output plus a manifest (schema, row count, gate result, metric versions) — the manifest is the one-source-of-truth pointer consumers read, never a hand-picked file |
| `run_demo.py` | End-to-end run of the whole pipeline with a JSON summary |

## How to run

```bash
python -m pytest tests/ -q
python run_demo.py
```

## Demo results (as of 2026-11-20)

- 17 rows ingested from 3 sources into 3 raw partitions
- 6 policies cleansed, 2 quarantined (missing premium; unparseable date), 0 duplicates
- 6 fact rows; metrics: 5 active policies, $27,350 total active premium, $5,470.00 average active premium, 0.8333 active share, 1.00 average 30-day activity
- Quality gate passed (completeness, uniqueness, range, referential integrity, freshness within 1-day SLA)
- Dashboard dataset published: 6 rows, partition `date=2026-11-20`

## Honest limits

- Local, single-process, standard-library-only Python — not AWS at scale. The S3/EMR/Spark/Redshift/Snowflake mapping is architectural: partitioned JSONL stands in for Parquet on S3, and the pipeline stages mirror an EMR/Spark job's bronze → silver → gold flow. There is no real Spark, EMR, or cloud deployment here.
- Microsoft Power Platform (Power Apps / Power Automate / Power BI / Dataverse) is **not** implemented — that is the known gap for this role (see the application package NOTES.md).
- No machine-learning system is built: the JD's "deep understanding of ML systems" is covered by validation and feature-engineering work, not by owning an ML system in production.
- PII handling is rule-based classification + masking, not a full data-governance platform; the demo data is synthetic.
