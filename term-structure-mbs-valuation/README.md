# Term-Structure MBS Valuation

A small, dependency-light toolkit for interest-rate term-structure modeling
and US Agency MBS valuation, built the way a structured-products quant team
uses these models day to day:

- **Curve construction** (`curves.py`) — Nelson-Siegel and Svensson
  zero-curve fits to market yields (deterministic grid search over the decay
  parameters + least squares for the betas), discount factors, forward
  rates, and parallel bump scenarios.
- **Hull-White one-factor model** (`hull_white.py`) — short-rate model
  calibrated exactly to the initial curve via the standard
  `r(t) = x(t) + alpha(t)` decomposition; analytic zero-bond prices and
  Monte Carlo short-rate paths with pathwise discount factors.
- **Prepayment model** (`prepayment.py`) — PSA benchmark speeds (CPR ramp
  to 6% at month 30) scaled by a capped exponential refinancing-incentive
  multiplier driven by WAC minus the prevailing mortgage rate.
- **Pass-through pricing** (`mbs.py`) — monthly agency pass-through cash
  flows (net interest, scheduled principal, prepayments), static pricing on
  the curve, Monte Carlo pricing where each Hull-White path drives its own
  prepayments through the path's 10-year zero rate, and a bisection OAS
  solver.
- **Risk analytics** (`analytics.py`) — effective duration/convexity from
  curve bumps and named rate-scenario prices.
- **Prepayment model validation** (`prepay_validation.py`) — independent
  challenge of the agency prepayment model: turnover/refi decomposition,
  seasoning ramp, burnout decay, incentive-response monotonicity, and a
  forecast-vs-actual backtest with bias/MAE/RMSE and a tolerance check.

## Run

```bash
pip install -r requirements.txt
python run_valuation.py   # fits a sample curve and values a $250mm pool
pytest                    # 34 tests
```

## Design notes

- Everything is deterministic given a seed: curve fits use fixed grids, and
  Monte Carlo uses `numpy.random.default_rng(seed)`.
- The prepayment model is a transparent benchmark model (PSA + incentive),
  not a loan-level econometric model; the PSA multiple and the incentive
  sensitivity are explicit parameters so results are easy to challenge —
  the same standard a validation team would apply.
- With Hull-White volatility set to zero, Monte Carlo pricing collapses to
  static curve pricing; the test suite uses that identity, plus the OAS
  round-trip, as its main correctness checks.
