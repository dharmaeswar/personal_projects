# Compliance Model Risk Validator

Independent validation of the models a compliance team relies on — the
kind of second-line validation a Model Risk Office runs before a model
is approved for use and while it stays in production.

**All data is synthetic and seeded.** No real bank, customer, or
transaction data is used, and nothing here is a claim about any real
institution.

## The problem

A transaction-monitoring alert model that misses SAR-worthy activity
lets financial crime through; one that over-alerts drowns investigators
in false positives. A compliance model that flags one customer group
far more often than another is a fair-lending problem, not just a
performance problem. And a model risk office cannot defend models it
has not inventoried. This validator covers all three: outcomes,
fairness, and governance.

## What it validates

- **Champion model** (`alert_model.py`): logistic regression on scaled
  transaction features (amount, 7-day velocity, cross-border, night,
  new device, structuring proximity).
- **Challenger model**: gradient boosting classifier, benchmarked
  against the champion on the same test set.
- **Benchmark model**: base-rate predictor (overall SAR-worthy rate,
  no features).
- **Outcomes analysis** (`outcomes.py`): ROC-AUC, KS statistic,
  confusion matrix at the operating threshold, precision/recall/F1,
  decile capture, and calibration by predicted decile.
- **Threshold sensitivity** (`threshold.py`): alert volume, precision,
  recall and F1 at six candidate thresholds, plus the human-review
  burden in hours and team-days for the alert queue.
- **Ongoing monitoring** (`monitoring.py`): Population Stability Index
  (PSI) and score mean drift between the validation population and a
  later production population.
- **Fairness** (`fairness.py`): flag rate and SAR capture by customer
  group, disparate-impact ratio (four-fifths rule, 0.80), and the
  equal-opportunity (capture-rate) gap across groups.
- **Governance** (`governance.py`): a compliance model inventory with
  lifecycle stages and validation cadence by risk tier (High: 365 days,
  Medium: 730, Low: 1095), flagging overdue validation, missing owner,
  and open high-severity findings on models still in use.
- **Validation report** (`report.py`): the full pack — verdict,
  outcomes, decile capture, threshold trade-off, monitoring, fairness,
  governance gaps, and findings.

## Run it

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 run_validation.py   # prints the report, writes validation_report.txt
PYTHONPATH=. python3 -m pytest -q        # 23 tests
```

## Results (seeded demo, 6,000 synthetic transactions)

- Champion ROC-AUC **0.787**, KS **0.467**; challenger 0.776; benchmark 0.500.
- At the operating threshold (t=0.5): precision 0.617, recall 0.146, 60 alerts.
- Top scored decile captures **33.6%** of all SAR-worthy cases.
- Best F1 (0.426) at t=0.2 with 390 alerts — the threshold trade-off
  the validator hands to the model owner, with review burden priced
  (60 alerts = 20.0 review hours, 0.53 team-days at t=0.5).
- Monitoring: PSI 0.006, score mean drift 2.9% — no material drift.
- Fairness: disparate-impact ratio 0.834 (above the 0.80 four-fifths
  line), equal-opportunity gap 0.173.
- Governance: 2 of 3 inventoried models have gaps — the AML alert model
  is overdue for validation with an open high finding while in use, and
  the fair-lending pricing model has no owner.
- Verdict: **PASS**, no material findings on the alert model itself.

## Why this project is different from the others in the repo

`fraud-model-validation` validates a card-fraud scorer; `ccar-stress-loss-validation`
validates a loan-loss forecaster; `investment-model-governance-validator` governs
investment models. This one validates **compliance** models: AML alert triage with
SAR conversion, threshold-vs-review-burden pricing, fair-lending disparate-impact
checks, and a compliance-model inventory — the work of a Compliance Model Risk
team, not a fraud or credit-risk team.
