# Risk Reporting Automation

A portfolio project for a Risk Reporting Associate role (CTC & Liquidity
Risk Reporting style). It automates the daily risk-reporting workflow
over synthetic positions and market-risk data: ingest, limit checks,
liquidity-stress scenarios, exception queue, and a sign-off checklist,
ending in a regulatory-style risk report as text and CSV files that
open in Excel.

**All data is synthetic and seeded.** No real positions, portfolios,
limits, or bank data are used, and nothing here is a claim about any
real company or its systems.

## What it does

- **Ingest** — 126 synthetic positions (120 seeded random rows plus
  planted cases) across 5 desks (Rates, FX, Credit, Secured Funding,
  Liquidity Management) and 4 risk types (VaR, DV01, Concentration,
  Liquidity Gap), loaded into SQLite (`sqlite3`, standard library only).
- **Limit checks** — exposures are aggregated per desk and risk type
  (20 limits) in both Python and SQL, and the two aggregates are
  reconciled. Status bands: BREACH at >= 100% utilisation, WARNING at
  >= 90%, OK below 90%.
- **Liquidity stress** — three scenarios (Baseline, Adverse, Severe)
  apply run-off rates to outflows and haircuts to liquid assets, and
  report the coverage ratio (liquid assets / stressed outflows). A
  ratio below 1.00 is a liquidity breach.
- **Exception queue** — limit breaches, stress breaches, and invalid
  source rows are queued most-severe-first for review instead of being
  dropped or silently included.
- **Sign-off checklist** — five control steps (breaches reviewed,
  stress reviewed, exceptions cleared or escalated, figures
  reconciled, report distributed) that must be signed before the
  report goes out.
- **Report outputs** — `reports/risk_report.txt` plus CSV files
  (`limit_breaches.csv`, `stress_results.csv`, `exceptions.csv`,
  `signoff_checklist.csv`) that open directly in Excel.

## What it validates

- **Completeness**: every position has a desk, risk type, and exposure.
- **Validity**: negative exposures are rejected into the exception
  queue, never aggregated.
- **Referential integrity**: every position's desk/risk type must have
  a defined limit; rows without one are queued as exceptions.
- **Limits**: utilisation vs limit for all 20 desk/risk-type groups.
- **Reconciliation**: Python aggregates must match the SQL `GROUP BY`
  aggregates exactly (within 0.01); any mismatch fails the run.
- **Stress**: coverage ratio vs the 1.00 threshold in each scenario.

The fixture plants 2 limit breaches on purpose (Rates/VaR and
FX/Concentration) and 2 bad source rows (a negative exposure and a
desk with no limit). The toolkit must flag both breaches and queue
both bad rows.

## Results of a run

```
Positions processed: 126
Limits checked:      20 (5 desks x 4 risk types)
Breaches:            2 — Rates/VaR 130.0% (exposure $19,496,374.10 vs
                       limit $15,000,000.00), FX/Concentration 160.2%
                       (exposure $12,819,153.78 vs limit $8,000,000.00)
Warnings:            0
Exceptions queued:   5 (2 limit breaches, 1 stress breach, 2 bad rows)
Reconciliation:      PASS — Python and SQL aggregates match on all 20 groups

Liquidity stress (coverage ratio = liquid assets / stressed outflows):
  Baseline  78.00 / 55.00 = 1.42  PASS
  Adverse   74.10 / 70.00 = 1.06  PASS
  Severe    68.64 / 85.00 = 0.81  BREACH
```

## How to run

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python run_report.py
python -m pytest -q
```

`run_report.py` writes the SQLite database to
`risk_reporting.db`, the text report and CSVs to `reports/`, and
prints the summary above.

## Layout

```
risk_reporting/
  data.py        synthetic positions, limits, planted breaches/bad rows
  limits.py      utilisation, breach bands, validation, aggregation
  stress.py      liquidity-stress scenarios and coverage ratios
  pipeline.py    SQLite load, SQL GROUP BY aggregates, reconciliation
  report.py      text report + CSV outputs
  workflow.py    exception queue, sign-off checklist, scheduled-run summary
run_report.py    runner
tests/           20 pytest tests
```

## Honest limits

- The data is synthetic and small (126 positions); nothing here proves
  performance or correctness on a real book.
- The stress test is a simple coverage-ratio calculation, not a
  regulatory liquidity model (no LCR/NSFR calculation, no maturity
  ladder, no behavioural assumptions).
- The "scheduled run" is a function that prints a summary line, not a
  real scheduler; the sign-off checklist is a CSV, not a workflow
  system with approvals or audit trails.
- Built with Python, SQL (sqlite3), pytest, and data validation only.
  It does not use Alteryx, UiPath, or Tableau, and it claims no
  people-leadership experience.
