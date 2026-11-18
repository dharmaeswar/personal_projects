# Security Analytics Pipeline

A portfolio project for a Data Engineer, Security Analytics role. It
builds a small security-analytics pipeline the way a security data
platform team would: ingest security telemetry, normalize it into a
security data model, run data-quality checks, compute
control-effectiveness KPIs, flag anomalies, and collect evidence per
control — all in plain Python + SQL (`sqlite3`, standard library only).

**All data is synthetic and seeded.** No real users, hosts, logins, or
vulnerabilities are involved, and nothing here describes a real
organization or a real security posture. The controls are illustrative
examples of the kind of control a security-analytics pipeline would
measure; they are not an audit opinion, and no expertise in any
security framework or security tooling is claimed.

## What it does

- **Ingest** — synthetic security telemetry is staged raw, exactly as
  received: 316 identity login events, 153 cloud audit-log events, and
  60 vulnerability findings, plus 40 identities and 30 assets as
  dimensions.
- **Normalize** — staged rows are loaded into a small security data
  model in SQLite: `identities`, `assets`, one unified `events` table
  (login + audit), and `findings`. Every normalized row keeps its
  source event id, so lineage is a plain lookup (see `lineage.json`:
  518 entries).
- **Quarantine** — rows that fail a quality rule go to a quarantine
  table with the reason, instead of being dropped silently. 11 rows
  are quarantined: 3 duplicate event ids, 2 null identity references,
  3 unknown identity references, 2 unknown asset references, and
  1 finding with due date before discovered date.
- **Late data** — 2 login events dated before the Oct 1 watermark are
  valid data: they are normalized and flagged `late_arriving = 1`,
  not quarantined.
- **Data-quality checks** — 13 checks over the staged raw data:
  completeness, uniqueness, referential integrity, late events, and
  finding-date validity. 3 of 13 pass; the 10 failures are the planted
  bad rows, listed by id in the report.
- **Control-effectiveness KPIs** — computed from the normalized model
  with real SQL: MFA coverage, stale privileged access, MFA usage in
  successful logins, mean time to remediate findings, and overdue
  findings by severity.
- **Anomaly detection** — simple, explainable rules: impossible-travel
  logins, dormant privileged accounts, overdue findings, and
  failed-login bursts.
- **Evidence collection** — one evidence record per control stating
  what was checked, the counts behind the verdict, and pass/fail
  against a stated threshold (see `evidence_report.json`).

## Results of a run

```
Staged rows:          529 (316 logins, 153 audit events, 60 findings)
Normalized events:    460 (310 login + 150 audit)
Normalized findings:  58
Quarantined rows:     11
Late-arriving events: 2 (normalized, flagged)
Data-quality checks:  3 of 13 passed (10 fail as designed — planted rows)
Lineage entries:      518

MFA coverage (privileged):     75.0% (6 of 8)
MFA coverage (all identities): 92.5%
Successful logins with MFA:    95.2% (260 of 273)
Stale privileged access:       25.0% (2 of 8 dormant > 90 days)
Mean time to remediate:        6.3 days (20 remediated findings)
Overdue findings:              6 of 58 (10.3%), 38 still open

Anomalies flagged:
  Impossible-travel logins:    1 (id-003: New York -> Tokyo in 30 min)
  Dormant privileged accounts: 2 (id-001: 120 days, id-021: 100 days)
  Overdue findings:            6 (incl. 2 critical)
  Brute-force bursts:          1 (id-007: 6 failed logins in 6 min)

Evidence: 5 of 5 controls have evidence (100% completeness).
  All 5 controls FAIL their thresholds — as designed, because the
  planted gaps (2 privileged accounts without MFA, 2 dormant
  privileged accounts, 6 overdue findings, 2 anomalies, 11
  quarantined rows) are exactly what the pipeline is meant to surface.
```

## How to run

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python run_pipeline.py
python -m pytest -q
```

`run_pipeline.py` writes the SQLite database to
`security_tables/security_analytics.db`, `lineage.json`,
`evidence_report.json`, and a human-readable
`validation_report.txt` in the project root.

## Layout

```
security_analytics/
  data.py        synthetic telemetry (seeded) + planted violations
  schema.py      expected schemas for staged and normalized tables
  pipeline.py    staging -> normalized model in SQLite, quarantine, lineage
  checks.py      data-quality checks (each returns pass/fail + failing ids)
  kpis.py        control-effectiveness KPIs via SQL
  anomalies.py   impossible travel, dormant access, overdue, brute force
  evidence.py    evidence record per control, pass/fail vs threshold
  report.py      renders validation_report.txt
run_pipeline.py  runner
tests/           20 pytest tests
```

## Honest limits

- The data is synthetic and small (529 staged rows); nothing here
  proves performance at real telemetry scale.
- The detectors are simple rules (same identity, two countries, under
  an hour), not a behavioral model; they show the pipeline shape, not
  detection science.
- KPIs are descriptive measures of synthetic data, not a security
  posture assessment. The control names are illustrative; no
  framework expertise is claimed.
- SQLite stands in for a warehouse; the SQL patterns (joins,
  `GROUP BY`, aggregation) transfer, but the engine does not.
- Checks run on the full staged batch in Python; a production
  pipeline would run them incrementally and alert on failure-rate
  thresholds instead of only reporting them.
