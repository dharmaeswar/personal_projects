# Safety Intelligence Analytics

Trend detection, anomaly flags, severity-weighted risk scoring and a
plain-language Safety Intelligence briefing over synthetic flight-safety
event data — the Safety Management System (SMS) analytics problem in
miniature: turn large, messy safety and operational datasets into
credible, timely input for safety decisions.

Built for the Delta Air Lines — Sr. Data Scientist, Safety Intelligence
(Ref 34970) application.

**Demo project. Synthetic data only. Not a real airline system.**
No real airline, flight, incident or safety report is used or claimed.
Category names follow the shape of public safety reporting (unstable
approach, TCAS resolution advisory, runway excursion precursor, bird
strike, ground damage, maintenance finding) but every count, date and
narrative is generated locally with a fixed seed. Severity weights and
risk-matrix bands are stated demo assumptions, not a real airline's
risk matrix.

## What it does

- `safetyint/data.py` — seeded generator: 24 months of synthetic safety
  events across 6 categories with monthly flight counts as the exposure
  denominator. A documented drift (unstable-approach rate x1.8 from
  month 19) gives trend detection a real signal to find.
- `safetyint/trends.py` — monthly rates per 10,000 flights, 3-month
  rolling rates, least-squares trend slopes, baseline z-scores against
  the first 12 months, and emerging-risk flags (recent z >= 2 and a
  rising slope).
- `safetyint/anomaly.py` — IQR outlier detection on monthly rates, with
  the fence each flagged month crossed and its z-score, so a reviewer
  can check the flag without re-running the math.
- `safetyint/risk.py` — severity-weighted risk ranking (severity weight
  x recent rate, adjusted for trend) and an SMS-style risk-matrix cell
  (likelihood band x severity) for each category.
- `safetyint/report.py` — plain-language briefing in text and JSON: top
  risks, emerging risks with recommended review, anomalous months, and
  the latest-month risk matrix.
- `safetyint/cli.py` — `trends` / `anomalies` / `risks` / `briefing`
  subcommands (`briefing --json` for machine-readable output).

## Skills used

Only skills Dharma has verified: Python, pytest, SQL-style aggregation
(counts and rates computed in Python over structured records), data
validation, statistical analysis, Linux. This project does **not** claim
AWS SageMaker / S3 / Bedrock, Databricks, NLP or transformer/LLM work
in production — those are listed as gaps in the application notes, not
demonstrated here.

## Run it

```bash
python run_demo.py
python -m safetyint.cli trends
python -m safetyint.cli anomalies
python -m safetyint.cli risks
python -m safetyint.cli briefing
python -m safetyint.cli briefing --json
```

## Tests

```bash
python -m pytest
```

28 tests: data generation and repeatability, rate math, rolling means and
slopes, z-scores and emerging-risk detection (including the planted
drift), IQR anomaly flags, risk ranking and matrix cells, briefing text
and JSON, and CLI subcommands.
