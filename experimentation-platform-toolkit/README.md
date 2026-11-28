# Experimentation Platform Toolkit

End-to-end statistical tooling for running trustworthy A/B tests at scale —
the kind of toolkit a Senior Data Scientist on an Experimentation Platform
team builds and maintains: experiment design, variance reduction, sequential
monitoring, causal-inference estimators and Bayesian ship/no-ship rules.

**Honest note:** all data is synthetic and seeded (see
`exp_platform/data_gen.py`). Ground-truth parameters are written into the
generator so every estimate can be checked against a known answer. This is
a demo of the methods, not production experiment data and not a claim of
real experimentation-platform experience at Robinhood.

## What it does

1. **Experiment design** (`exp_platform/design.py`) — per-variant sample
   size for proportion and continuous metrics (two-sample normal
   approximation), minimum detectable effect by binary search, and a
   sample-ratio-mismatch (SRM) chi-square check on the observed split.
2. **CUPED variance reduction** (`exp_platform/cuped.py`) — optimal theta
   from the pre-period covariate, adjusted metric, and the share of
   variance removed.
3. **Group-sequential monitoring** (`exp_platform/sequential.py`) —
   O'Brien-Fleming alpha-spending boundaries (Lan-DeMets) across looks, so
   peeking does not inflate the false-positive rate, plus a per-look
   stop/continue decision.
4. **Causal inference** (`exp_platform/causal.py`) — difference-in-differences
   with a Welch t-test and 95% CI; a Beta-Binomial Bayesian A/B test with
   P(B > A) and expected-loss ship rules; a T-learner uplift model
   (one linear model per arm) returning per-user uplift and the ATE.
5. **One-call report** (`exp_platform/report.py`) — `experiment_report`
   runs the design check, naive test, SRM check, CUPED, Bayesian call and
   sequential decision on one experiment and returns a plain dict.
6. **Commercial measurement** (`exp_platform/commercial.py`, added
   Nov 2026) — the measurement half of a commercial data-science role:
   a geo-holdout estimator that reads the incremental volume of a
   promotion from treated vs holdout territories (DiD plus the total
   incremental volume), and a linear channel-attribution model that
   splits fitted promotional contribution across rep visits, emails and
   samples, controlling for pre-period sales. `commercial_measurement_report`
   runs both on one synthetic HCP panel (territories, pre/post
   prescription volumes, touches by channel) and returns a plain dict.

## Results (seeded run — `python run_demo.py`)

- Synthetic A/B test: 20,000 users per variant, baseline 10%, true lift
  +0.8pp. Observed lift +0.77pp (z = 2.42, p = 0.016) — recovers the truth.
- SRM check: no mismatch (p = 1.000, balanced 50/50 split).
- CUPED: theta = 0.056, variance reduction 3.1% on this binary outcome
  (the pre-period covariate is only weakly correlated with a binary
  conversion), adjusted lift +0.65pp (z = 2.08).
- Bayesian: P(B > A) = 0.992, expected loss of shipping B = 0.00001 —
  a ship call under a 0.0005 loss threshold.
- Sequential (look 5 of 5): O'Brien-Fleming boundary 1.96, crossed.
- Design: 22,855 users per variant needed to detect +0.8pp at 80% power;
  MDE at the current n is 0.86pp.
- DiD panel (200 units, true effect 5.0): estimate 4.80, p < 0.0001.
- Geo-holdout promotion (40 territories, 600 HCPs, true lift 12.0 TRx
  per treated territory): estimate +11.85 TRx, p < 0.0001, total
  incremental 237 TRx across 20 treated territories — recovers the truth.
- Channel attribution on the same panel (R² = 0.90, pre-period sales
  controlled): rep visits 72.4%, samples 17.9%, emails 9.6% of fitted
  promotional contribution. True per-touch effects are rep visits 0.9,
  samples 0.5, emails 0.15 TRx; the fitted coefficients are 0.98, 0.48
  and 0.09.

## How to run

```bash
pip install -r requirements.txt
python run_demo.py        # prints the full workflow on seeded data
python -m pytest -q       # 25 tests
```

## Layout

- `exp_platform/design.py` — sample size, MDE, SRM check
- `exp_platform/cuped.py` — CUPED adjustment
- `exp_platform/sequential.py` — O'Brien-Fleming boundaries
- `exp_platform/causal.py` — DiD, Bayesian A/B, T-learner uplift
- `exp_platform/data_gen.py` — seeded synthetic data + ground truth
- `exp_platform/report.py` — one-call `experiment_report`
- `exp_platform/commercial.py` — geo-holdout impact, channel attribution
- `tests/test_design.py`, `tests/test_platform.py`,
  `tests/test_commercial.py` — 25 tests

## Honest limits

- The CUPED gain here is small (3.1%) because a binary conversion is
  only weakly predictable from the pre-period activity score; on a
  continuous revenue metric with a strongly correlated pre-period value
  the same code removes far more variance (see `test_cuped_reduces_variance`).
- The Bayesian and sequential rules use the standard textbook
  assumptions (Beta(1,1) prior, equally spaced looks). The T-learner
  uses plain linear models — transparent and fast, not a tuned ML model.
- The commercial panel is synthetic HCP-shaped data (territories,
  prescription volumes, touch counts), not real claims, patient, HCP or
  sales data. Attribution is linear: it splits fitted contribution
  across channels and does not claim channels act independently, and it
  controls for pre-period sales — without that control the channel
  coefficients are unstable because baseline volumes vary far more
  across HCPs than the per-touch effects.
- No real user data, no live experiment, no Robinhood affiliation.
