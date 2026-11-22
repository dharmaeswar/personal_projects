# Investment Model Governance Validator

Validates the investment models a second-line Model Risk Management team
oversees — alpha/signal models, portfolio construction and optimisation,
risk models, trading and asset-allocation models, and AI/ML-enabled
investment workflows — the way an independent reviewer would: effective
challenge, outcomes analysis, backtesting, and governance of the model
inventory.

**All data is synthetic and seeded.** No real Vanguard, market, or client
data is used, and nothing here is a claim about any real institution.

## What it validates

- **Alpha / signal models** (`signals.py`): Pearson and Spearman
  information coefficient, IC decay across 1d/5d/20d horizons, signal
  turnover, hit rate, and information ratio.
- **Portfolio construction** (`portfolio.py`): long-only minimum-variance
  optimisation with per-name caps (projected-gradient solver, NumPy
  only), volatility vs equal weight, Sharpe ratio, Herfindahl
  concentration, and a pass/fail effective-challenge checklist.
- **Risk models** (`risk.py`): historical VaR and expected shortfall,
  exception counting, the Kupiec proportion-of-failures test, and the
  Christoffersen independence test for clustered breaches.
- **Asset allocation** (`allocation.py`): risk-parity weights, risk
  contributions, diversification ratio, and maximum drawdown.
- **Model governance** (`governance.py`): a model-inventory register with
  lifecycle stages, validation cadence by risk tier, governance-gap
  detection (overdue validation, missing owner, High findings in use),
  an eight-point effective-challenge checklist, and an SR 11-7-style
  validation report with an overall opinion.

## How it differs from the other validation projects in this repo

- `cross-asset-model-validation-suite` checks pricing-model invariants
  (parities, no-arbitrage bounds) for rates, FX and equity models.
- `model-validation-toolkit` is a generic outcomes/sensitivity/drift
  toolkit.
- `fraud-model-validation` and `ccar-stress-loss-validation` validate
  credit and fraud scoring models.
- This project is the only one that validates **investment** models —
  alpha signals, portfolio optimisers, VaR backtests, asset allocation —
  and the **governance** layer around them (inventory, lifecycle,
  validation cadence, effective challenge, SR 11-7 reporting).

## Run the tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## Run the full validation

```bash
PYTHONPATH=. python -m investment_governance --out validation_report.json
```

Writes `validation_report.json` with the signal, portfolio, risk,
allocation and governance results on seeded synthetic data.
