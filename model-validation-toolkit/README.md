# Model Validation Toolkit

Small Python toolkit for independent model validation work:

- **Outcomes analysis** (`outcomes.py`) — back-test summary: bias, MAE, RMSE, hit rate within a 5% band.
- **Sensitivity analysis** (`sensitivity.py`) — bump-and-revalue table for a pricing or scoring function.
- **Drift checks** (`drift.py`) — mean drift in basis points and Population Stability Index (PSI).
- **Pricing-model surveillance** (`surveillance.py`) — GARCH(1,1) volatility estimation and forecasts,
  PCA on a yield-curve panel, rolling-window diagnostic statistics, out-of-sample backtests with
  threshold/residual analysis, and a CUSUM-style structural-break check.
- **Rating-model & criteria validation** (`ratings.py`) — PD monotonicity across grades, per-grade
  default back-tests against implied PDs (binomial z-test), year-on-year transition-matrix stability,
  criteria-input data-aging checks, and upgrade / downgrade / default migration summaries.
- **Options-pricing model validation** (`options.py`) — Black-Scholes
  call/put pricing, implied volatility by bisection, put-call parity checks,
  Greeks (delta, gamma, vega, theta, rho), and book-level validation of
  observed marks against model prices with breach and parity flags.

## Run the tests

```bash
pip install pytest
PYTHONPATH=. pytest -q
```

## Run the options-pricing checks demo

```bash
PYTHONPATH=. python3 run_options_check.py   # seeded synthetic option book, prints a validation summary
```

## Run the rating checks demo

```bash
PYTHONPATH=. python3 run_ratings_check.py   # synthetic rating book, prints a validation summary
```

Built to match model risk management practice: independent challenge, outcomes
analysis, sensitivity testing, and documented, reproducible checks.
