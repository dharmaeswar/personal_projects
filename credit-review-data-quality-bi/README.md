# Credit Review Data Quality & BI

A portfolio project for the Capital One **Principal Associate, Data Analyst –
Credit Review** role (Req R1005985). It covers the three work types in that
job description — Innovation, Business Intelligence and Data Management —
over a synthetic credit-review portfolio.

**All data is synthetic and seeded.** No real bank, customer, or loan data is
used, and nothing here is a claim about any real institution.

## The problem

A Credit Review team needs to trust the data behind its findings. Reviews
arrive from a workflow system, loans from an origination system, and
findings pile up across business units. Before any dashboard is believed,
the data has to be checked (completeness, uniqueness, validity,
referential integrity), every metric has to trace back to its source
tables (lineage), every governed field needs a plain-language definition,
and access to sensitive data has to be controlled. This project does all
four, then builds the BI dashboard on top of the checked data.

## What it does

- **Data quality monitoring** (`credit_review_bi/quality.py`) — 9 checks
  over loans, reviews and findings: completeness of risk rating and
  outstanding balance, loan-id uniqueness, non-negative balances,
  ratings in 1–6, cycle days in 1–90, findings pointing at real reviews,
  reviews pointing at real loans, severity in the allowed set. Each
  failing check names the exact rows that failed. A data-quality score
  (share of checks passing) feeds the dashboard.
- **Metadata, lineage and business definitions** — every dashboard metric
  maps to its source tables, and every governed field has a
  plain-language business definition.
- **Data-access governance** (`credit_review_bi/governance.py`) — a
  metadata catalog (owner, source system, sensitivity, retention) and a
  role-based governor: analysts read Internal data, auditors read
  Restricted data only for an audit purpose, admins have full access.
  Every decision is logged.
- **BI dashboard** (`credit_review_bi/metrics.py`) — portfolio by segment
  and risk rating, reviews by outcome and type, median review cycle
  time, overdue reviews, open/overdue findings by severity and category,
  plus the data-quality score. `run_bi.py` writes `dashboard_report.txt`
  and `dashboard_metrics.csv`.

A few bad rows are planted on purpose (a duplicated loan id, a negative
balance with a missing rating, an orphan finding) so the checks have real
defects to catch — the dashboard honestly reports the failures instead of
hiding them.

## How to run

```bash
python -m pytest -q          # test suite
python run_bi.py              # writes dashboard_report.txt + dashboard_metrics.csv
```

`run_bi.py` exits non-zero while any quality check fails, so it can sit
behind a scheduled job or CI gate. Standard library only; pytest is the
only test dependency.

## Files

- `credit_review_bi/data.py` — seeded synthetic loans, reviews, findings
- `credit_review_bi/quality.py` — quality checks, score, lineage, definitions
- `credit_review_bi/governance.py` — metadata catalog, access governor
- `credit_review_bi/metrics.py` — dashboard metrics and text report
- `run_bi.py` — entry script (report + CSV)
- `tests/` — pytest suite (data, quality, metrics, governance)
