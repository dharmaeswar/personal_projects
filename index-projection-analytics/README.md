# Index Projection Analytics

Forward-looking index projections for a free-float market-cap-weighted
equity index — the work the BlackRock Index Projection & Analytics team
does: index methodology, forward-looking index projections, corporate
actions, index rebalances, benchmark analysis, and advanced analytics.

Built as the role project for the BlackRock — Index Projections &
Analytics, Associate (Req R267111, Atlanta) application.

**All data is synthetic and seeded.** Nothing here describes a real
index, real constituents, real corporate actions, or real BlackRock
analytics. Tickers AAA–HHH are invented.

## What it does

- **Index level** (`index_projection/universe.py`) — free-float market
  capitalisation divided by a divisor; the divisor is set so the level
  starts at 1000.
- **Corporate actions** (`index_projection/corporate_actions.py`) —
  stock splits (shares and price move in opposite directions, divisor
  unchanged), cash dividends and spin-offs (price drops, divisor
  rescaled so the index level is continuous).
- **Projected rebalances** (`index_projection/rebalance.py`) — rank
  current constituents plus eligible candidates by free-float market
  cap, take the top N, and report additions, deletions, projected
  weights and one-way turnover (half the sum of absolute weight
  changes).
- **Forward projections** (`index_projection/projection.py`) —
  projected index level under per-constituent return scenarios, plus
  benchmark-relative analysis: excess returns, tracking error
  (population standard deviation of daily excess returns, annualised
  by sqrt(252)) and the information ratio.

## How it differs from the other projects in this repo

- `cross-asset-model-validation-suite` validates pricing-model
  invariants for rates, FX and equity derivatives.
- `performance-measurement-engine` measures realised fund performance
  (TWR, Modified Dietz, IRR, benchmark-relative realised returns).
- `investment-data-validation-suite` validates security-master, trade
  and yield data quality.
- This project is the only one that projects an index *forward*: the
  divisor mechanics of corporate actions, a projected rebalance with
  turnover, and scenario-driven index levels.

## Run it

```bash
python -m index_projection        # demo: actions, rebalance, scenarios
python -m pytest tests/ -q        # 8 tests
```

Demo output (seeded 8-name universe, base level 1000):

- After a 2-for-1 split of AAA, a $1.50 BBB dividend and a $12 CCC
  spin-off, the index level stays at 1000.00 — the divisor absorbs
  each action, as index methodology requires.
- Projected rebalance adds candidate III and drops GGG and the spun-off
  CCCS, with one-way turnover of 19.33%.
- Projected levels: base case (+2% broad) 1019.64; growth rally
  1020.25; broad sell-off 950.89. (The base case is below 1020.00
  because the spun-off CCCS carries no return in the scenario map and
  is held flat.)
- Seeded six-day index vs benchmark series: annualised tracking error
  0.40%, information ratio 1.04.

## Honest limits

- No real index data, no live prices, no corporate-action feed: every
  input is a hand-seeded example.
- The divisor model is the textbook free-float market-cap method; real
  index providers add free-float bands, liquidity screens, capping and
  buffer rules that this project does not implement.
- Tracking error and the information ratio are computed on six seeded
  daily observations — far too few for a real estimate.
- No Aladdin, Bloomberg or FactSet integration.
