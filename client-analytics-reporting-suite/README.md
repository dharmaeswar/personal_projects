# Client Analytics Reporting Suite

A portfolio project for a Client Quantitative Analyst role (Bank of America
style). It turns synthetic client, transactional, operational and
performance data into the reporting a Client Quantitative Analyst delivers
every day: KPI dashboards, trend analysis, and a stakeholder summary —
with the data validation, quality assurance and reconciliation that keeps
the numbers trustworthy.

**All data is synthetic and seeded.** No real clients, accounts,
transactions or bank data are used, and nothing here claims any
affiliation with Bank of America or any real company.

## What it does

- **Extract & integrate** — 60 clients, ~90 accounts, 601 transactions
  (May–Oct 2026) and 120 operations events across 4 channels and 3 client
  segments, generated with a fixed seed and loaded into SQLite.
- **Validate & QA** — every transaction is checked for negative or missing
  amounts, duplicate transaction ids, and orphan accounts (accounts whose
  client does not exist). Bad rows go to an exception queue for review;
  they are never silently dropped or included in the KPIs.
- **Reconcile** — monthly-by-channel totals are computed independently in
  Python and in SQL (`GROUP BY`); the run fails if the two disagree by
  more than 0.01.
- **Analyze** — monthly KPIs (transaction count, volume, average ticket,
  active accounts), month-over-month volume change, KPIs by channel,
  top 10 clients by volume, and operations-event resolution times.
- **Report** — dashboard CSVs that open directly in Excel
  (`kpi_by_month.csv`, `kpi_by_channel.csv`, `top_clients.csv`,
  `ops_summary.csv`, `exceptions.csv`), a plain HTML dashboard
  (`dashboards/dashboard.html`), and a short stakeholder summary
  (`dashboards/summary.txt`).

## What it validates

- **Completeness**: every transaction has an amount, account and month.
- **Validity**: negative and missing amounts are rejected to the queue.
- **Uniqueness**: duplicate transaction ids are caught (first copy kept).
- **Referential integrity**: accounts must belong to a known client.
- **Reconciliation**: Python aggregates must match SQL aggregates exactly.
- **Trends**: month-over-month volume change is computed from valid rows only.

The fixture plants 3 bad transactions on purpose (one negative amount,
one missing amount, one duplicate id) plus one orphan account. The
pipeline must flag all of them and exclude them from every KPI.

## Run it

```bash
python run_dashboard.py
python -m pytest -q
```

## Results of a run

```
Transactions processed: 601 (593 valid, 9 exceptions queued for review).
Total valid volume: $2,559,161.42 across 593 transactions.
Dashboard files written to dashboards: dashboard.html, exceptions.csv,
kpi_by_channel.csv, kpi_by_month.csv, ops_summary.csv, summary.txt,
top_clients.csv
```
