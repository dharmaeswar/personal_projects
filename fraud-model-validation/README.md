# Fraud-Detection Model Validation

A portfolio project for a Quantitative Model Validation role. It validates a
card-transaction fraud-scoring model the way a model-validation team would:
outcomes analysis, calibration, ongoing monitoring, and fairness slices.

**All data is synthetic and seeded.** No real bank, cardholder, or
transaction data is used, and nothing here is a claim about any real
institution.

## What it validates

- **Champion model**: logistic regression on scaled features.
- **Challenger model**: gradient boosting classifier.
- **Benchmark model**: base-rate predictor (overall fraud rate, no features).
- **Outcomes analysis**: ROC-AUC, KS statistic, confusion matrix at an
  F1-tuned threshold, precision/recall/F1, and decile rank-ordering
  (fraud capture per decile).
- **Calibration**: mean predicted vs observed fraud rate by predicted decile.
- **Ongoing monitoring**: Population Stability Index (PSI) and mean drift
  per feature between train and test.
- **Fairness**: flag rate and fraud capture by region, with the maximum
  flag-rate gap across regions.
- **Safeguards analytics** (new, Nov 2026): precision/recall at operating
  thresholds for a harm-detection model, false-positive review burden in
  human-review hours, score drift monitoring, and a decision audit trail
  with overturn rates.
- **Transaction-risk scoring** (new, Nov 2026): engineered transaction
  features (velocity ratio, night/new-device flags, cross-border x
  card-not-present interaction, amount z-score), delayed-label evaluation
  (fraud labels mature only after chargebacks arrive), adversarial pattern
  checks (fraud-share shifts by segment, baseline vs recent), measured
  model-quality vs scoring-latency trade-off, and model-regression
  monitoring with per-metric tolerances.
- **Credit-risk analytics** (new, Nov 2026): seeded synthetic personal-loan
  applications with bureau scores, utilisation, inquiries and delinquencies;
  score-band bad rates and the bureau-score Gini; decision-cutoff analysis
  (approval rate, approved bad rate, bad capture at cutoffs 620–680);
  vintage bad rates by booking month; and 30-to-90 DPD roll rates.

## How to run

```bash
pip install -r requirements.txt
python run_validation.py
```

This prints the validation report and writes it to `validation_report.txt`.

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```

## Layout

- `fraud_validation/data.py` — seeded synthetic transaction generator
- `fraud_validation/models.py` — champion / challenger / benchmark models
- `fraud_validation/metrics.py` — ROC-AUC, KS, confusion matrix, deciles, calibration
- `fraud_validation/monitoring.py` — PSI and mean drift
- `fraud_validation/fairness.py` — slice metrics by region
- `fraud_validation/safeguards.py` — harm-detection analytics: precision/recall
  at thresholds, false-positive review burden, drift monitoring, audit trail
- `fraud_validation/transaction_risk.py` — transaction-risk scoring:
  engineered features, delayed-label evaluation, adversarial pattern
  checks, quality-vs-latency trade-off, model-regression monitoring
- `fraud_validation/credit_risk.py` — credit-risk analytics: bureau
  features, score-band performance and Gini, decision cutoffs, vintage
  analysis, 30-to-90 DPD roll rates
- `fraud_validation/report.py` — plain-text validation report writer
- `run_validation.py` — CLI entry point
- `tests/` — pytest test suite
