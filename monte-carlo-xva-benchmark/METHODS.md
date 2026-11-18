# Model Documentation — Monte-Carlo XVA Benchmark Framework

Written in the spirit of SR 11-7 (Guidance on Model Risk Management):
purpose and intended use, methodology, assumptions, limitations, and
validation evidence are documented so an independent reviewer can
reproduce, challenge, and bound the model's outputs.

## 1. Purpose and intended use

The framework produces indicative exposure profiles (EE, EPE, PFE) and
valuation adjustments (CVA, FVA, KVA) for a small portfolio of forwards
and European options, and — its primary purpose — **benchmarks the Monte
Carlo engine against independent closed-form values** so that
implementation error is detected before any number is relied upon. It is
a development/validation tool, not a production pricing or regulatory
capital system.

## 2. Methodology

### 2.1 Market simulation

Each underlier follows geometric Brownian motion under the risk-neutral
measure, stepped exactly (lognormal) on a uniform time grid:

    S(t+dt) = S(t) * exp((r - sigma^2/2) dt + sigma * sqrt(dt) * Z),  Z ~ N(0,1)

Asset classes: equity index (S0=100, sigma=20%), FX rate (S0=1.10,
sigma=8%), commodity (S0=75, sigma=30%). Default run: 10,000 paths,
50 steps, 5-year horizon, master seed 42. Each asset class draws from its
own RNG stream spawned from the master seed (`SeedSequence.spawn`), so
results are reproducible and independent of execution order or
parallelism.

### 2.2 Portfolio and mark-to-market

Per asset class (one netting set each): a long forward and a long
European call, struck at spot, maturing at the horizon, with notionals of
roughly 100k currency units. Mark-to-market along paths:

- Forward: `V(t) = S(t) - K * exp(-r (T - t))`
- Call: Black-Scholes value with remaining maturity `T - t`
  (intrinsic value at expiry).

### 2.3 Exposure

Discounted exposure `E(t) = exp(-r t) * max(V(t), 0)`, then

- **EE(t)** = path mean of `E(t)`;
- **PFE(t)** = 97.5% path quantile of `E(t)` (quantile configurable);
- **EPE** = trapezoidal time-average of EE over the horizon.

### 2.4 XVA

- **Default term structure**: flat hazard rate `h`; survival
  `S(t) = exp(-h t)`; bucket default probability
  `dPD_i = S(t_{i-1}) - S(t_i)`.
- **CVA** = `LGD * sum_i EE(t_i) * dPD_i` (EE already discounted).
- **FVA** = `funding_spread * sum_i EE(t_i) * dt_i` — a funding-cost
  proxy on the uncollateralised positive exposure profile.
- **KVA**: capital proxy `K(t) = capital_fraction * PFE(t)`;
  **KVA** = `cost_of_capital * sum_i K(t_i) * dt_i`.

Outputs are reported as a cumulative ladder at 1–5 year horizons, per
asset class and in total.

### 2.5 Parallel execution

Asset-class simulations are independent work items executed with
`concurrent.futures.ProcessPoolExecutor` (a serial fallback is available
via `--serial`; joblib provides the same fan-out pattern and was used
interchangeably during development). Parallelism changes wall-clock time
only, never results.

### 2.6 Benchmarking (outcomes analysis)

Two independent checks per asset class, each compared with a relative
tolerance band (default **1.2%**, configurable):

1. **Option price**: Black-Scholes price at t=0 vs the Monte Carlo
   discounted mean payoff, using 200,000 antithetic paths.
2. **Forward EE**: closed-form expected exposure of a long forward under
   GBM (Black-style formula on the lognormal underlier) vs simulated EE
   at the mid-horizon bucket, 200,000 antithetic paths.

Antithetic variates and the large benchmark path count keep the Monte
Carlo standard error roughly an order of magnitude below the tolerance
band, so a failure indicates implementation error rather than sampling
noise.

## 3. Assumptions

- Risk-neutral GBM with constant volatility and a constant risk-free
  rate per run; no dividends, convenience yield, or foreign rate (the FX
  class is modelled as a generic GBM asset).
- Flat hazard rate, constant LGD, deterministic funding spread and
  cost of capital; no wrong-way risk (exposure and default independent).
- No collateral, margining, netting across asset classes, or close-out
  netting effects; each asset class is its own netting set.
- No early exercise, path-dependent payoffs, jumps, or stochastic
  volatility / rates.
- PFE uses the discounted exposure distribution; the KVA capital figure
  is a simple proxy (fraction of PFE), **not** a regulatory (e.g. SA-CCR
  or IMM) capital calculation.

## 4. Limitations

- GBM understates tail exposure for assets with jumps or volatility
  clustering; PFE figures should be read as lower-bound style estimates
  for such underliers.
- The flat-hazard CVA ignores credit-spread term structure and
  exposure/default correlation; FVA uses a single spread and the positive
  exposure profile only (no negative-exposure funding benefit, no DVA).
- Monte Carlo error is controlled but non-zero; benchmark checks quantify
  it for the two covered quantities only. Quantities without a closed
  form (e.g. PFE of the option leg) are validated indirectly through the
  exposure-engine unit tests and profile sanity properties.
- Results are indicative and unsuitable, without substantial extension,
  for regulatory reporting, limit setting, or trade pricing.

## 5. Validation evidence

- Unit/integration tests (`tests/`, 24 tests): GBM first/second moments
  vs lognormal theory, Black-Scholes put-call parity and expiry
  behaviour, exact exposure values on synthetic inputs, XVA sign /
  monotonicity / linearity properties (hazard rate, LGD, funding spread,
  cost of capital), ladder consistency with totals, seed
  reproducibility, and both benchmark checks inside the 1.2% band.
- Every CLI run re-executes the benchmark checks and exits non-zero if
  any check falls outside the tolerance band.
