# Enterprise Core Datasets Pipeline

A portfolio project for a **Data Engineer** role (Enterprise Core Datasets;
also the FIS Data Engineer II role project, Nov 27, 2026). It builds the
trusted datasets an Enterprise Core Datasets team owns: AI usage and cost,
Unit Economics (revenue vs cost drivers), Jira enterprise-application data,
payment settlement and reconciliation, and critical metrics (Gross Booking
Value, Revenue).

**All data is synthetic and seeded (seed 42).** No real company, customer, or
booking data is used, and nothing here is a claim about any real institution.

## Problem statement

Finance, product, and engineering teams need trusted answers — "how much are
we spending on AI tools, and who is driving it?", "what is the margin on each
dollar of revenue?", "what is Jira delivery throughput by project?", "did
every authorised payment settle, and how fast, by rail?" — but the
sources disagree: AI usage events arrive with re-delivered batches and bad
rows, tool prices change mid-quarter, Jira data comes from an enterprise app
outside the platform, bookings must reconcile to the penny, and the payments
gateway re-delivers batches and reports settlements a day or two late. Raw feeds
cannot answer those questions directly.

This project fixes that with an enterprise datasets pipeline:

- **Source contracts** (`enterprise_core/contracts.py`) — every feed has a
  schema (required fields, types, allowed values, ranges, date window).
  Contract breaks are quarantined with a reason, never silently loaded.
- **Bronze ingest** (`enterprise_core/pipeline.py`) — append-only Parquet,
  window-function dedupe (`ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY
  ingested_seq DESC)`), so re-delivered batches collapse to one row.
- **Dimensional models** — `dim_tool` is **SCD Type 2** on unit price
  (copilot-pro $3.00/1k tokens until 2026-10-31, $2.50 after, so a fact
  always joins the price in force on its event date); `dim_team` is SCD
  Type 1; `dim_date`; `dim_cost_category` (hosting / support / payment).
- **Facts** — `fact_ai_usage_daily` (tool × team × day, with tokens, events,
  cost, and the point-in-time price), `fact_unit_economics_daily` (one row
  per day: GBV, revenue, total cost, margin), `fact_cost_daily` (one row per
  day × cost category), `fact_jira_weekly` (open issues and story points by
  project × status, weekly snapshot), `fact_payments_daily` (date × payment
  method × status: transaction count, gross and settled amounts, average
  settlement lag — settled amounts never exceed gross, and lag is reported
  only on settled rows).
- **Incremental loads** — each fact has a watermark (max source date loaded);
  re-running the pipeline inserts 0 new rows (idempotent).
- **Data quality** (`enterprise_core/quality.py`) — schema, completeness,
  uniqueness, ranges, referential integrity (including the SCD2
  point-in-time join), SCD2 single-current-row invariant, reconciliation
  (fact AI cost vs bronze, fact GBV vs bronze, cost facts vs unit
  economics, fact payments gross/settled/txn-count vs bronze), and a
  freshness SLA (newest fact within 2 days of the run date). A failed check
  blocks publish.
- **Orchestration** (`enterprise_core/orchestration.py`) — the pipeline as a
  DAG (ingest → dims → facts → checks) with topological ordering, one retry
  for transient failures, and resume: a re-run with the same run id skips
  tasks that already succeeded with the same inputs.
- **Backfills** (`enterprise_core/backfill.py`) — a backfill plans from
  lineage (which facts depend on the affected source), deletes only the
  fact rows in the range, rebuilds them from bronze, re-runs the checks, and
  commits only if they pass; on failure it rolls back to the old rows.
- **Lineage** — every table records its upstream sources
  (`Warehouse.lineage_for`), so a backfill or an incident review starts from
  the dependency graph, not from memory.
- **Analytics** (`enterprise_core/analytics.py`) — reporting queries over the
  gold tables only: AI cost by tool/month and by team, unit-economics trend,
  Jira throughput, GBV vs revenue, payments settlement by method (gross vs
  settled, settlement rate, average lag).

## Runs locally, without a Spark cluster

This project runs locally with pandas + Parquet. It does **not** pretend a
cluster run happened. Every pandas operation names the Spark operation it
mirrors, so the same code maps one-to-one onto a real Spark job — swap the
DataFrame calls for Spark equivalents and the logic is unchanged.
`requirements.txt` lists only pandas, pyarrow, pytest.

## Layout

```
enterprise_core/
  contracts.py      source contracts per feed
  seed.py           synthetic feeds (seed 42) with planted defects
  pipeline.py       bronze ingest, dims (SCD2), facts, incremental loads, lineage
  quality.py        checks, reconciliation, freshness SLA
  orchestration.py  DAG runner: order, retry, resume
  backfill.py       lineage-planned backfills with validation cutover
  analytics.py      reporting queries over gold tables only
  run.py            end-to-end run: DAG -> Parquet -> run_report.json
run_pipeline.py     entry point
tests/              pytest suite (contracts, pipeline, quality, orchestration, backfill, analytics)
```

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py
python -m pytest -q
```

## Results (real run, Nov 27, 2026)

```
checks: 33/33 passed
facts added: fact_ai_usage_daily=1120, fact_unit_economics_daily=56,
             fact_cost_daily=168, fact_jira_weekly=86, fact_payments_daily=627
gbv/revenue: total_gbv_usd=97,814,200.92, total_revenue_usd=11,754,826.49,
             revenue_share_of_gbv_pct=12.02, avg_margin_pct=51.61
payments settlement: wire 327 txns, $792,380.25 gross / $377,730.14 settled (47.67%);
             card 295 txns, $749,195.72 / $351,227.99 (46.88%);
             ach 306 txns, $747,193.06 / $320,957.26 (42.96%);
             wallet 297 txns, $662,196.45 / $339,132.83 (51.21%)
```

Ingest (seeded run):

| feed | received | good | quarantined | duplicates removed |
| --- | --- | --- | --- | --- |
| ai_usage | 4,466 | 4,458 | 8 | 4 |
| jira_issues | 244 | 240 | 4 | 0 |
| bookings | 58 | 56 | 2 | 0 |
| payments | 1,233 | 1,227 | 6 | 2 |

The 8 quarantined AI rows are 3 null teams, 2 negative token counts,
2 unknown tools, and 1 future date; the 4 duplicates are re-delivered
event_ids. The 2 quarantined bookings are 1 revenue-above-GBV row and
1 negative hosting cost. The 6 quarantined payments are 2 negative amounts,
1 unknown method (crypto), 1 settled amount above the authorised amount,
1 failed transaction carrying a settled amount, and 1 future date; the
2 duplicates are re-delivered gateway txn_ids. AI cost is spread almost evenly across the five
teams (19.2%–20.6% each), and copilot-pro's October cost per 1k tokens is
$3.93 — above its $3.00 list price because cost covers both input and output
tokens while that metric divides by input tokens only. Settlement rates sit
near 43–51% by method because only settled transactions carry settled money;
authorised and captured transactions are still in flight, and failed ones
settle nothing — the rate is a pipeline-health signal, not a loss.

## Tests

31 tests, all passing (`python -m pytest -q`): contract validation and
quarantine reasons, dedupe and idempotent ingest, SCD2 price history and
point-in-time joins, fact totals tying back to bronze, incremental loads
inserting 0 rows on re-run, reconciliation catching a tampered fact,
freshness failing on a stale fact, DAG ordering / retry / resume / cycle
rejection, backfill planning from lineage, backfill recomputing identical
totals and committing, backfill rolling back when checks fail, and
analytics totals tying to the facts. The payments feed adds 6 tests:
contract quarantine reasons for each defect type, gateway dedupe, fact
grain tying to bronze (counts, gross, settled), dim coverage, all checks
passing with the new fact plus backfill planning for it, and settlement
summary rates staying in [0, 100].
