# Commodity Derivatives Pricing & Risk

Pricing and risk analytics for commodity derivatives, built for a
front-office Commodities Quant role (Citi Markets Quantitative
Analytics style): futures curves, Black-76 options on futures,
Greeks, VaR and scenario analysis, with the validation checks a
model-risk team would run.

**All data is synthetic and seeded.** Spot paths are simulated with
geometric Brownian motion from a fixed seed (natural gas carries a
winter seasonal); no real market data is used, and nothing here is a
claim about any real price, curve, or return.

## What it does

1. **Simulates spot paths** (`commodities/data.py`): 252 trading
   days for WTI crude, Henry Hub natural gas and gold.
2. **Builds futures curves** (`commodities/curves.py`): cost of
   carry F(T) = S * exp((r + u - y) * T), calendar spreads,
   contango/backwardation shape, and the implied convenience yield
   backed out of the curve.
3. **Prices options on futures** (`commodities/pricing.py`): Black-76
   calls and puts, closed-form delta/gamma/vega, finite-difference
   theta, implied volatility by bisection, and a Monte Carlo pricer
   on the driftless futures measure. Only the standard library is
   used (`math.erf` for the normal CDF); no SciPy.
4. **Measures book risk** (`commodities/risk.py`): historical VaR
   and expected shortfall by replaying simulated return days,
   Monte Carlo VaR with fresh simulated paths (independent shocks —
   labelled as an approximation), and scenario shocks (spot moves,
   vol bumps) that reprice the whole book.
5. **Validates the models** (`commodities/validation.py`):
   put-call parity (an arbitrage identity, must hold to 1e-8),
   Monte Carlo convergence to Black-76 within 3 standard errors,
   and closed-form Greeks versus finite differences.

## How to run

```bash
python run_commodities.py
python -m pytest -q
```

`run_commodities.py` writes a human-readable
`commodities_report.txt` in the project root.
