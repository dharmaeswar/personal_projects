# Monte-Carlo XVA Benchmark Framework

A self-contained Python framework that simulates Monte Carlo exposure paths
across asset classes, computes credit / funding / capital valuation
adjustments (CVA, FVA, KVA), and **benchmarks every headline number against
an independent closed-form value within a 1.2% tolerance band**.

Built as a model-validation style exercise: the simulation engine and the
benchmark engine are independent implementations, and the run only passes
when they agree.

## What it does

1. **Simulation** — geometric Brownian motion paths (exact lognormal
   stepping, seeded RNG) for three asset classes with distinct parameters:
   an equity index, an FX rate, and a commodity. Default: 10,000 paths,
   50 time steps over a 5-year horizon.
2. **Portfolio** — per asset class (each treated as its own netting set):
   one long forward and one long European call, struck at spot, maturing at
   the horizon. Positions are marked to market along every path.
3. **Exposure** — discounted expected exposure **EE(t)**, expected positive
   exposure **EPE**, and potential future exposure **PFE(t)** at the 97.5%
   quantile, per time bucket.
4. **XVA** — 
   - **CVA** from the EE profile, a flat hazard-rate default term structure
     and LGD;
   - **FVA** from a funding spread applied to the EE profile;
   - **KVA** from a capital proxy (a configurable fraction of PFE) times a
     cost-of-capital rate.
   Results are reported as a **cumulative XVA ladder** at 1–5 year horizons,
   per asset class and for the total portfolio.
5. **Benchmarking** — two independent closed-form checks per asset class:
   - Black-Scholes call price at t=0 vs the simulated discounted payoff mean;
   - analytic expected exposure of the forward under GBM vs simulated EE at
     the mid-horizon bucket.
   Each check reports its relative error against the tolerance band
   (default **1.2%**, `--tolerance`) with pass/fail.
6. **Stochastic projection & capital market assumptions** (`xva_benchmark/cma.py`)
   — building-block expected returns; Bayesian posterior expected returns
   from a prior view plus history; Ledoit-Wolf-style correlation shrinkage;
   private-market NAV paths with scheduled capital calls and distributions;
   and VaR / CVaR tail risk on terminal outcomes. See the "Stochastic
   projection" section below.
7. **Parallel execution** — asset classes are simulated concurrently with
   `concurrent.futures.ProcessPoolExecutor` (joblib is an interchangeable
   alternative for the same fan-out pattern). Per-asset RNG streams are
   spawned from the master seed, so serial and parallel runs are identical.

## Quick start

```bash
pip install -r requirements.txt

# Full run: prints the XVA ladder + benchmark verdicts, writes
# output/results.json and output/xva_ladder.csv
python -m xva_benchmark
# or
python run_benchmark.py --paths 10000 --steps 50 --seed 42

python -m pytest tests/ -q
```

Useful flags: `--serial` (disable parallelism), `--tolerance 0.012`,
`--hazard-rate 0.02`, `--funding-spread 0.015`, `--horizon 5`,
`--outdir output`.

## Stochastic projection and capital market assumptions

```python
import numpy as np
from xva_benchmark.cma import (
    building_block_expected_return, cma_from_history,
    project_cash_flows, tail_risk,
)
from xva_benchmark.simulation import time_grid

# Building-block expected return: cash + inflation + real growth + premium.
building_block_expected_return(0.02, 0.025, 0.015, 0.04)  # 0.10

# Bayesian CMAs: prior view + 120 months of history, shrunk correlations.
rng = np.random.default_rng(0)
history = rng.normal(loc=[0.006, 0.004], scale=[0.04, 0.03], size=(120, 2))
cma = cma_from_history(history, prior_means=[0.004, 0.003],
                       prior_vols=[0.01, 0.01])

# Private-market NAV projection: $100m NAV, $20m call at year 3, $30m
# distribution at year 5; tail risk on terminal NAV.
proj = project_cash_flows(100.0, 0.08, 0.15, time_grid(5.0, 10),
                          n_paths=5000, seed=7,
                          capital_calls={6: 20.0}, distributions={10: 30.0})
risk = tail_risk(proj["nav"][:, -1], confidence=0.95)
```

## Project layout

```
xva_benchmark/
    config.py       asset classes, simulation and XVA configuration
    simulation.py   GBM path generation (seeded, antithetic terminal draws)
    pricing.py      normal CDF, Black-Scholes, analytic forward EE
    portfolio.py    forward / call positions and mark-to-market
    exposure.py     EE / EPE / PFE profiles
    xva.py          CVA / FVA / KVA and the cumulative ladder
    benchmark.py    independent closed-form benchmark checks
    cma.py          building-block / Bayesian CMAs, private-market NAV
                    projection with calls and distributions, VaR / CVaR
    runner.py       parallel orchestration, reporting, CLI
tests/              pytest suite (pricing, simulation, exposure, XVA,
                    benchmarks, CMAs and stochastic projection)
METHODS.md          methodology, assumptions and limitations (SR 11-7 style)
```

## Documentation

See [METHODS.md](METHODS.md) for the model documentation: intended use,
methodology, assumptions, limitations, and the outcomes-analysis /
benchmarking approach, written in line with SR 11-7 model risk management
expectations.

## Requirements

Python 3.12, numpy; pytest for the test suite. No other dependencies.
