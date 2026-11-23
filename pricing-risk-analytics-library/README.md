# Pricing & Risk Analytics Library

A small, dependency-free Python library for pricing and risk analytics —
the kind of analytics library a quantitative team builds for a trading
business: closed-form pricing, PDE solvers, Monte Carlo, discount curves,
and portfolio risk. Pure standard library (tests need pytest).

## What it does

- **Black-Scholes** (`pricing_lib/black_scholes.py`) — European call/put
  prices, all five Greeks, and implied volatility by bisection.
- **PDE solvers** (`pricing_lib/pde.py`) — explicit and Crank-Nicolson
  finite-difference solvers for the Black-Scholes PDE. The explicit
  scheme refuses an unstable step instead of returning garbage; the
  Crank-Nicolson system is solved with the Thomas algorithm.
- **Monte Carlo** (`pricing_lib/monte_carlo.py`) — European and arithmetic
  Asian option pricers under risk-neutral GBM, with antithetic variates,
  standard errors and 95% confidence intervals. Seeded, so every run is
  reproducible.
- **Discount curves** (`pricing_lib/curves.py`) — bootstrap discount
  factors from annual par swap rates; log-linear interpolation, zero
  rates, forward rates, and a re-pricing check that recovers each input
  par rate.
- **Portfolio risk** (`pricing_lib/risk.py`) — historical VaR and expected
  shortfall, delta-normal (parametric) VaR, and Greeks aggregation over a
  book of positions.

## How it differs from the other projects in this repo

- `cross-asset-model-validation-suite` independently reprices derivatives
  and compares them with vendor marks — a *validation* suite. This is a
  *pricing library*: the pricers themselves (PDE solvers, Monte Carlo,
  curves, risk), built to be imported and reused.
- `monte-carlo-xva-benchmark` is a Monte Carlo engine for XVA exposure.
  This library covers the full pricing stack (closed form, PDE, Monte
  Carlo, curves, VaR) for a trading book.
- `model-validation-toolkit` validates models (outcomes, GARCH, drift,
  ratings). This library builds the models a validation team would check.

## Run it

```bash
python3 run_demo.py                 # price the demo book three ways, bootstrap a curve, measure risk
PYTHONPATH=. python3 -m pytest tests/ -q   # 25 tests
```

Demo output: the three pricers agree to within a few cents on every leg
of the book; the bootstrapped curve re-prices every input par swap rate
exactly; VaR/ES are reported on a synthetic return series.
