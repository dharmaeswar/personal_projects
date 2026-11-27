# ERM / RCSA Technology Risk Analytics

A portfolio project for an Enterprise Risk Management (ERM) Senior Data
Analyst role at a bank. It runs the core ERM workflow on synthetic data:
maintain an RCSA risk register, test controls (Test of Design / Test of
Effectiveness), track KRIs and KPIs against thresholds, assess 1LOD
functions against industry frameworks, and produce a technology-risk
report with Power BI-ready dashboard rows.

**All data is synthetic and seeded.** No real losses, controls, vendors,
or bank data are used, and nothing here is a claim about any real
company or its systems.

## What it does

- **RCSA register** — 14 risks across IT, Information Security, Third
  Party, and Data Management sources. Inherent risk = likelihood x impact
  (1–25 scale, Low / Medium / High bands). Residual risk applies the
  strongest mapped control, with weak Test of Effectiveness results
  halving a control's design effectiveness.
- **Controls testing** — 16 controls with design ratings and ToE samples.
  A control counts as Effective only with a sound design AND a ToE pass
  rate of 90% or more. The planted failing case is C-09 (annual restore
  test): design Ineffective, 5 exceptions in 8 samples.
- **KRI / KPI dashboard** — 8 KRIs with six quarters of history, warning
  and breach thresholds, and emerging-risk detection (three straight
  quarters worsening). Planted breaches: unpatched critical
  vulnerabilities (24 vs a breach threshold of 20) and vendor SLA
  breaches (5 vs 5).
- **Framework assessment** — 12 requirements mapped to COBIT, NIST,
  ITIL, DCAM, and DMBOK, scored Met / Partial / Not Met with
  weight-weighted coverage per framework and per 1LOD function.
- **Integrated reporting** — loss events, risks, controls, and KRI
  readings are stored in SQLite; Python aggregates are reconciled
  against SQL aggregates and the run fails on any mismatch. Outputs are
  a text risk report plus CSVs (`rcsa_results.csv`, `kri_dashboard.csv`,
  `dashboard.csv`, `exceptions.csv`, `framework_assessment.csv`,
  `signoff_checklist.csv`) that open in Excel or import into Power BI.
- **Exception queue** — breaches, High residual risks, and failed
  controls are queued most-severe-first for review instead of being
  dropped or silently included.
- **Sign-off checklist** — five control steps that must be signed before
  the report goes out.

## What it validates

- **Scoring**: inherent = likelihood x impact; residual never exceeds
  inherent; a risk with no control keeps its full inherent score.
- **Controls**: ToE pass rates from samples; design alone never makes a
  control Effective.
- **KRIs**: threshold bands in both directions (higher-worse and
  lower-worse); emerging-risk trend detection.
- **Frameworks**: weighted coverage math; unknown requirements and
  invalid statuses rejected.
- **Reconciliation**: Python loss totals must match SQL `GROUP BY`
  totals exactly, per category; negative loss amounts are rejected.
- **Determinism**: the same seed always produces the same dataset.

## Run it

```bash
python run_report.py        # writes erm_rcsa.db and reports/
python -m pytest tests/ -q  # 28 tests
```

Python standard library only; pytest is the only test dependency.
