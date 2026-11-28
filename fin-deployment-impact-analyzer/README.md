# Fin Deployment Impact Analyzer

A forward-deployed data science toolkit for measuring an AI customer
agent's impact at strategic customers — built as a portfolio project
for an Intercom (Fin) Senior Forward Deployed Data Scientist
application: embed with customers, build enterprise Fin deployments,
measure the impact, and feed what is learned back into the product.

**All data is synthetic and seeded.** No real customers, conversations,
or Intercom/Fin data is used. No model API calls: Fin's resolutions
are simulated from seeded rates, so every run is reproducible offline.
This is a demo of the measurement method — not a claim about any real
deployment, customer, or Fin result.

## The problem

"Fin is live" is not a result. A customer needs to know, with numbers
and uncertainty attached, whether resolutions went up, handle time
went down, escalations fell, and CSAT held — and the product team
needs to know which channels and intents still struggle. This toolkit
does that loop: SQL metrics from the conversation store, before/after
statistics, a plain-language customer summary, and product feedback
from the same numbers.

## What it does

- **Synthetic conversations** (`fin_impact/data.py`) — 2,000 seeded
  conversations across 5 customers and 3 channels, before and after
  the Fin deployment, with resolution, handle time, CSAT, escalation.
- **SQL analysis** (`fin_impact/sql_analysis.py`) — resolution
  (automation) rate, handle time, CSAT, escalation rate, overall and
  per customer and per channel, all in SQL against SQLite.
- **Statistics** (`fin_impact/stats.py`) — Wilson intervals, Welch's
  t-test, and uplift with a 95% interval (standard library only).
- **Deployment readiness** (`fin_impact/deploy.py`) — a scored
  readiness checklist and the measurement plan handed to the customer
  at kickoff (metrics, baseline, cadence, success rule).
- **Reports** (`fin_impact/report.py`) — plain-language customer impact
  summary and product feedback notes from the same numbers.

## Run it

```bash
python run_analysis.py                 # in-memory demo run
python run_analysis.py --db fin.db     # persist the conversation store
python -m pytest -q                    # tests
```

Demo run (seeded, 2,000 conversations): resolution rate 0.0 before
-> 0.511 after (uplift 0.511, 95% CI 0.480 to 0.542), mean handle time
16.05 min before -> 9.9 min after, escalation rate 0.285 -> 0.083,
mean CSAT 3.52 -> 4.12; per-customer and per-channel tables in
`outputs/per_customer.csv`.

## Skills used

Only skills Dharma has verified: Python, SQL (SQLite), statistics,
data validation, PyTest, Git. No conversational-AI, LLM-evaluation,
or Fin production experience is claimed — the LLM-eval gap is flagged
honestly in the application notes.
