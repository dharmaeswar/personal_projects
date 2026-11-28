# Clinical EMR Analytics

A portfolio project for the **HCA Healthcare — Senior Product Analyst
(Nashville, TN, Job 18510129)** application. It builds the analytics the
posting describes over synthetic EMR data: ingest clinical feeds,
standardize them to a common vocabulary, apply data-quality rules with
quarantine, run root-cause analysis on the defects, compute clinical
quality measures, and publish standardized reports and a dashboard —
across the full data-analytics project lifecycle (requirements,
design, implementation, support).

**All data is synthetic and seeded.** Patient references are opaque
`PAT-###` IDs; there are no names, dates of birth, MRNs, or real health
records. Nothing here is a claim about any real company's systems, and
nothing here is healthcare employment experience — it is a demo-scale
analytics pipeline, not a production clinical system.

## What it does

- **Ingest** (`emr_analytics/ingest.py`) — loads four CSV feeds
  (encounters, vitals, labs, medications). Malformed rows are reported
  with line number and reason, never silently dropped.
- **Standardize** (`emr_analytics/standardize.py`) — maps the feeds to
  one common vocabulary before anything is judged: Fahrenheit vitals
  convert to Celsius, lab aliases (`HGB`, `A1C`, `LDL`) map to
  canonical test names, medication doses convert to milligrams where
  the unit allows it. Ranges are always applied in canonical units.
- **Quality rules** (`emr_analytics/quality.py`) — six named rules:
  unknown encounter, future timestamp, out-of-range value, duplicate
  observation, lab result before collection, invalid dose. A failing
  row is quarantined with every rule that caught it; nothing invalid
  reaches the measures or the dashboard.
- **Root-cause analysis** (`emr_analytics/root_cause.py`) — groups
  quarantined rows by feed and rule, ranks them, and attaches a
  candidate cause and a suggested fix for each pattern. Causes are
  labelled candidates, not proven facts.
- **Measures** (`emr_analytics/measures.py`) — vitals completeness
  (83.33%), median lab turnaround (3.79 hours), medication
  reconciliation coverage (100%), data-quality pass rate (87.5%),
  return visits within 30 days (25%). Each is a documented
  denominator/numerator pair over clean rows only.
- **Reports and dashboard** (`emr_analytics/reports.py`) — four
  standardized report definitions (daily quality snapshot, lab
  turnaround, medication reconciliation, data-quality register) and a
  Tableau / Power BI-style dashboard spec, rendered as a static HTML
  dashboard. BigQuery Standard SQL for the same measures lives in
  `emr_analytics/sql/measures.sql`.
- **Lifecycle** (`emr_analytics/lifecycle.py`) — requirements, design,
  implementation, and support run as explicit phases with a run log,
  so a failed run can be resumed and audited.

## Demo

```bash
python run_pipeline.py
```

Runs the full lifecycle on `data/` and writes `output/run_report.json`,
`output/dashboard.html`, and `output/dashboard_spec.json`. On the
seeded data: 96 rows loaded, 12 quarantined (5 vitals, 4 labs,
3 medications), 4 measures computed, 10 root-cause findings.

## Tests

```bash
python -m pytest
```

31 tests: ingest/standardization, every quality rule, quarantine
counts, root-cause ranking, all five measures, the four report
definitions, the dashboard render, the BigQuery SQL structure, and
the full lifecycle with artifacts.

## Honest limits

- Synthetic demo data; the feeds are small CSVs, not live EMR extracts.
- The dashboard is a static HTML page, not a live Tableau/Power BI
  workbook; the SQL is reference BigQuery SQL, not executed against
  BigQuery.
- The return-visit rate is a 30-day return proxy, not a clinical
  readmission rate — the data has no admission/discharge linkage.
- Root causes are candidate explanations from the defect pattern,
  not findings confirmed with a source-system owner.
