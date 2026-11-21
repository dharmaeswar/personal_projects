# Performance Measurement Engine

A performance measurement engine for private-markets funds — the kind of
calculation engine a Quantitative Developer on a performance team builds:
time-weighted returns (TWR), Modified Dietz, money-weighted returns (IRR),
NAV roll-forward reconciliation, benchmark-relative returns with proxy
fills, and gross-to-net fee bridges.

Built as a portfolio project for an MSCI Quantitative Developer
application (performance measurement systems, GIPS-adjacent methods,
private markets). All fund data is synthetic and seeded; nothing here
describes a real fund, real NAVs, or real GIPS verification work.

## What it does

- **Returns** (`perf/returns.py`) — TWR as chain-linked sub-period
  returns split at every external flow; Modified Dietz with
  day-weighted flows; money-weighted return (IRR) solved by bisection
  on the NPV function. Every method is a pure, auditable function over
  conserved cash flows.
- **NAV roll-forward** (`perf/nav.py`) — period-over-period NAV
  decomposition (beginning NAV + contributions − distributions +
  income + gains = ending NAV) that reconciles exactly, with no plug or
  balancing entry.
- **Benchmark-relative returns** (`perf/benchmark.py`) — arithmetic and
  geometric excess returns, plus proxy-filled returns for periods or
  assets where no direct benchmark exists.
- **Gross/net** (`perf/fees.py`) — fee and carry leg selection with a
  fully explainable gross-to-net bridge (management fee, carry above a
  hurdle, net gain).
- **Composite returns** (`perf/composite.py`) — GIPS-adjacent composite
  arithmetic: asset-weighted composite return from beginning market
  values, equal-weighted return, and equal-weighted dispersion across
  the composite's portfolios. Computation only; it claims no GIPS
  verification work.
- **Validation** (`perf/validation.py`) — timing conventions and
  flow-classification rules, checked against the value-neutrality
  property they depend on: a flow timed at a period boundary must not
  change the period return. Includes deliberately adversarial timing
  edge cases (same-day flows, boundary flows, zero NAV) as golden-value
  regression tests.
- **Composites** (`perf/composite.py`) — GIPS-adjacent composite
  returns: asset-weighted composite return, equal-weighted return, and
  equal-weighted dispersion across portfolios in a composite.

## Run it

```bash
pip install -r requirements.txt   # pytest only; the engine is stdlib-only
python run_demo.py                 # full demo: TWR, Dietz, IRR, NAV roll-forward, benchmark, fees
```

## Tests

```bash
python -m pytest tests/ -q
```

Tests are golden-value regression tests: hand-computed TWR, Modified
Dietz, IRR, NAV reconciliation, proxy-fill, and gross-to-net cases,
including adversarial timing edge cases that an implementation must
reproduce exactly.
