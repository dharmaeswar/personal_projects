# Cross-Asset Model Validation Suite

A regression-validation framework for pricing and risk models across three
asset classes — **interest rates, FX, and equity**. It encodes the analytic
invariants every correct implementation must satisfy (parities, no-arbitrage
bounds, monotonicity, curve properties) and evaluates them over parameterized
stress and scenario grids defined in YAML. Any breach is reported before the
offending model change is merged, instead of surfacing downstream in pricing
or risk numbers.

Built with pure Python 3.12 + NumPy + PyYAML. No other dependencies.

## What it checks

| Asset class | Models under test | Invariants |
|---|---|---|
| Interest rates | Discount curve (log-linear DF interpolation), par-yield bootstrapping, Vasicek short-rate bond pricing | DFs in (0, 1]; DFs strictly decreasing; bootstrapped curve reprices par bonds to par; zero-coupon prices within (0, face]; Vasicek price → face as τ → 0; Vasicek price decreasing in the short rate |
| FX | Outright forwards, Garman–Kohlhagen options | Covered interest-rate parity (forward vs. curve-implied forward); put–call parity across strikes; forward increasing in the domestic rate |
| Equity | Black–Scholes calls/puts and deltas | Put–call parity across strikes; call and put no-arbitrage bounds; call monotonicity in strike and spot; delta bounds ([0, 1] calls, [−1, 0] puts) |

## Project structure

```
cross-asset-model-validation-suite/
├── configs/
│   └── scenarios.yaml          # base inputs + stress grids (rate / vol / spot shocks)
├── model_validation_suite/
│   ├── __main__.py             # CLI: python -m model_validation_suite
│   ├── models/
│   │   ├── rates.py            # DiscountCurve, bootstrap, Vasicek bond price
│   │   ├── fx.py               # FX forward, Garman-Kohlhagen
│   │   └── equity.py           # Black-Scholes price and delta
│   ├── invariants/
│   │   ├── framework.py        # registry, Outcome, scenario runner
│   │   ├── rates_invariants.py
│   │   ├── fx_invariants.py
│   │   └── equity_invariants.py
│   ├── scenarios.py            # YAML loading + grid expansion
│   └── report.py               # JSON / CSV pass-fail summaries
├── tests/                      # pytest suite (models, framework, reporting)
├── run_validation.py           # convenience wrapper around the CLI
└── requirements.txt
```

## Running the suite

```bash
pip install -r requirements.txt

# Full run over configs/scenarios.yaml (writes reports/summary.json + summary.csv)
python -m model_validation_suite
# or
python run_validation.py --config configs/scenarios.yaml --out-dir reports

# Tests
python -m pytest tests/ -q
```

The CLI exits with status 1 if any check fails, so it can gate a CI pipeline
or a pre-merge hook.

### Example output

```
Cross-Asset Model Validation Suite
Config:    configs/scenarios.yaml
Scenarios: 22
Checks:    96  Passed: 96  Failed: 0  Pass rate: 100.0%
  equity   45/45 passed
  fx       27/27 passed
  rates    24/24 passed

Wrote reports/summary.json
Wrote reports/summary.csv
```

### Summary reports

Every run writes two artifacts into `reports/`:

- **`summary.json`** — totals, pass rate, per-asset-class breakdown, the full
  result list, and a `breaches` array with measured value vs. limit and a
  human-readable detail for each failure.
- **`summary.csv`** — one flat row per check
  (`scenario_id, asset_class, invariant, status, measured, limit, detail`).

Both use stable schemas designed for dashboard ingestion — e.g. loading
`summary.csv` into **Power BI** gives a live pass/fail dashboard of model
regression coverage by asset class and scenario.

## Scenario grids

`configs/scenarios.yaml` holds base model inputs per asset class plus shock
grids — parallel curve shifts in basis points for rates, and spot × vol shock
combinations for FX and equity. The runner expands each grid (Cartesian
product) and evaluates every invariant of that asset class at every grid
point. Adding stress coverage means adding values to the YAML — no code
changes — and runs are fully repeatable from the config alone.

## Adding a new model or invariant

The framework is a registry: an invariant is one decorated function that
receives the scenario context dict and returns an `Outcome`.

```python
# model_validation_suite/invariants/rates_invariants.py
from .framework import Outcome, invariant

@invariant("rates", "forward_rates_positive",
           "Implied forward rates stay positive across the curve.")
def forward_rates_positive(ctx):
    curve = ctx["curve"]
    # ... compute the measured quantity and compare it with its limit ...
    return Outcome(passed=worst <= 0.0, measured=worst, limit=0.0,
                   detail=f"largest negative forward: {worst:.3e}")
```

Registering the function is enough — the runner, the JSON/CSV reports and the
CLI pick the new check up automatically for every scenario of that asset
class. New models follow the same pattern: add the pricer under
`models/`, add its invariants under `invariants/`, and extend the YAML grid.

## License

MIT
