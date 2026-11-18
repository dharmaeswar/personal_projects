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
6. **Parallel execution** — asset classes are simulated concurrently with
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
    runner.py       parallel orchestration, reporting, CLI
tests/              pytest suite (pricing, simulation, exposure, XVA, benchmarks)
METHODS.md          methodology, assumptions and limitations (SR 11-7 style)
```

## Documentation

See [METHODS.md](METHODS.md) for the model documentation: intended use,
methodology, assumptions, limitations, and the outcomes-analysis /
benchmarking approach, written in line with SR 11-7 model risk management
expectations.

## Requirements

Python 3.12, numpy; pytest for the test suite. No other dependencies.
