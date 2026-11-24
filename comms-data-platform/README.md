# Comms Data Platform

A portfolio project for an **Amazon Software Development Engineer, Data,
Communications Tech** role. It builds the platform the Comms Tech team
runs: a serverless-style data lake / warehouse for internal communications
data, with ETL from internal systems and vendor APIs, a data catalog,
and a serving layer that answers web applications and AI agents — through
both a read API and MCP tools.

**All data is synthetic and seeded (seed 42).** No real company, campaign,
or engagement data is used, and nothing here is a claim about any real
institution. No AWS services are actually called: the lake is local
Parquet files, the "Glue job" is pandas code that names the Spark
operation it mirrors, and the "CDK stack" is a declarative manifest.
The code says so wherever it matters.

## Problem statement

Comms teams need trusted answers — which campaigns reached people, how
engagement trends by channel, what to send next — but the data lives in
two places that disagree: an internal system holding messages and
campaigns, and a vendor API returning engagement metrics. Raw vendor rows
are messy (duplicates, unknown campaigns, negative counts), the vendor
API fails transiently and rate-limits, and downstream consumers (a web
app, an AI agent) need one governed place to ask questions — not raw
files.

This project fixes that with a lakehouse plus a serving layer:

- **Ingest** — an internal-system extract plus a paginated vendor API
  client with per-page retry (page 2 fails once on purpose) and a
  rate-limit counter. Raw rows land in bronze, nothing cleaned.
- **Validate** — schema enforcement before any write lands; quality
  checks quarantine bad rows with the rule that fired (duplicate
  message id, null campaign id, future send date, negative metric,
  unknown campaign). A retry path re-checks corrected rows and promotes
  the ones that pass.
- **Transform** — a PySpark-style job (pandas locally, every operation
  names its Spark equivalent) builds gold `daily_engagement`:
  messages joined to metrics, grouped by date/campaign/channel, with
  open rate. Gold reconciles back to silver exactly.
- **Catalog** — a Glue Data Catalog model: datasets registered with
  owner, schema, partitions and location. Nothing is served unless it
  is registered here first.
- **Serve** — a read-only query engine (Athena-style: SELECT only,
  writes rejected) behind a REST-style API, plus an MCP tool server
  (`list_datasets`, `describe_dataset`, `query_dataset`) that AI
  agents call through a JSON-RPC envelope. Unknown tools and bad
  arguments return structured errors, never exceptions.
- **Orchestrate** — a Step Functions-style state machine
  (ingest → validate → transform → catalog → observe) with retries,
  resume by run id, and dead-letter recording for failed steps.
- **Infrastructure as code** — a CDK-style stack manifest (S3 buckets,
  Glue jobs, state machine, Lambda functions, DynamoDB serving cache,
  Athena workgroup, CloudWatch alarms) with a validator that checks
  required properties the way a synth review would.
- **Observe** — canaries (gold exists, has rows, open rate in range,
  gold reconciles to silver, catalog covers gold), alarms (critical on
  canary failure, warning on quarantined rows) and an ORR checklist
  gate that must pass before a release ships.

## Layout

```
comms_platform/
  connectors.py      internal source + paginated vendor API (retry, rate limit)
  lake.py            bronze -> silver -> gold on Parquet, schema enforcement, delta log
  quality.py         quality checks, quarantine, retry, gold/silver reconciliation
  transforms.py      PySpark-style gold build (daily engagement)
  catalog.py         Glue Data Catalog model (register / search / describe)
  query.py           Athena-style read-only SQL over gold (SQLite)
  serving.py         read API + MCP tool server (JSON-RPC)
  orchestration.py   Step Functions-style state machine (retries, resume, DLQ)
  iac.py             CDK-style stack manifest + validator
  observability.py   canaries, alarms, ORR checklist
  pipeline.py        end-to-end wiring (ingest -> observe)
run_pipeline.py      run the pipeline into ./comms_tables
run_demo.py          demo the API + MCP serving layer
tests/               31 pytest tests
```

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py --out comms_tables   # lake, catalog, validation report
python run_demo.py --out comms_tables       # API + MCP answers against gold
python -m pytest tests/ -q                  # 31 tests
```

## Verified result (Nov 24, 2026)

- 31/31 tests pass.
- Pipeline: 15 bronze messages + 14 bronze metrics in; 12 + 12 silver
  rows out; 5 rows quarantined (duplicate id, null campaign, future
  date, negative metric, unknown campaign); 10 gold rows, reconciled
  to silver with zero mismatches.
- Canaries: 5/5 pass. Alarms: one warning (quarantined rows present),
  no critical alarms. ORR gate: PASSED. IaC stack validates clean.
- Vendor API: 4 calls for 3 pages (one transient failure retried).
