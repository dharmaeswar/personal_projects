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
- **Model approval workflow** (new, Nov 2026): a model-inventory record and
  an approval gate over the validation evidence — ROC-AUC, KS, outcomes
  sample size, calibration gap, worst feature PSI, and fairness flag-rate
  gap are checked against documented thresholds and resolve to APPROVED,
  APPROVED_WITH_CONDITIONS (soft breaches become follow-up conditions), or
  NOT_APPROVED (hard breaches block), with a validator sign-off trail.
- **Financial-flow reconciliation** (new, Nov 2026): a seeded ledger of
  5,000 postings reconciled against downstream flow records — match by
  transaction id, flag amount mismatches, missing and orphan records, and
  duplicate postings; per-product capital-flow totals (card purchases,
  refunds, payouts, fees) and aging of unresolved breaks; 75 breaks
  (1.50% of ledger), under the 2% control threshold.
- **Card-fraud rule backtesting** (new, Nov 2026): five card-fraud rules
  (1h velocity burst for card testing, cross-border card-not-present
  high amount, new-device night activity, high amount, 24h velocity
  surge) backtested on the synthetic test set with fraud capture,
  precision, false positives, fraud loss avoided and review cost per
  rule; a challenger rule set compared against the champion set in
  shadow mode (decisions recorded, not enforced); a staged-rollout
  simulation at 10/25/50/100% exposure; model-score threshold tuning
  that minimises total cost (false positives x $25 review cost plus
  missed fraud dollars); and KRIs — fraud rate in bps, flag rate,
  false-positive rate, fraud loss per $1,000 processed, approval rate
  and fraud capture — for an executive-ready view.
- **Partner decision science targeting & approval models** (new, Nov 2026):
  seeded synthetic partner-offer impressions with bureau features and
  per-product-type click affinity; a conversion-propensity targeting
  model (logistic champion vs gradient-boosting challenger, ROC-AUC,
  KS, decile conversion capture/lift); a Platt-calibrated approval
  model with calibration by decile and an approval-certainty split;
  next-best-offer ranking by predicted conversion x calibrated
  approval probability, scored with NDCG@3 against a popularity
  baseline; and a seeded A/B readout for model-ranked targeting vs
  the popularity control (Welch t-test, bootstrap 95% CI on the
  conversion lift, approval-rate guardrail, approvals per 1,000
  members). Seeded run: champion ROC-AUC 0.700, top decile converts
  at 52.9% vs a 25.2% base rate; ranking NDCG@3 0.486 vs 0.461
  baseline; A/B lift +2.48pp (p=0.0118) with the approval guardrail
  breached — conversion-only targeting pulled in more marginal
  members, so offers are ranked by conversion x approval probability.

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
- `fraud_validation/approval.py` — model approval workflow: inventory
  record, evidence gates with documented thresholds, approval decision,
  sign-off trail
- `fraud_validation/rule_backtesting.py` — card-fraud rule backtesting:
  rule definitions, per-rule backtest, shadow test, staged-rollout
  simulation, score-threshold tuning on false positives vs fraud loss,
  KRIs, report section builder
- `fraud_validation/targeting.py` — partner decision science targeting
  and approval models: conversion-propensity champion/challenger,
  Platt-calibrated approval model with certainty split, next-best-offer
  ranking (NDCG@3 vs popularity baseline), A/B readout with Welch
  t-test, bootstrap CI and approval-rate guardrail
- `fraud_validation/report.py` — plain-text validation report writer
- `run_validation.py` — CLI entry point
- `tests/` — pytest test suite
