# Systematic Futures & FX Signal Research

Researches systematic trading signals the way a quantitative research
team would: build signals, backtest them with realistic costs, combine
them into a risk-managed portfolio, and then stress-test whether the
edge survives out-of-sample data, higher costs, and delayed execution.
The focus is futures and FX — the markets Graham Capital's systematic
strategies trade — with trend, carry, and mean-reversion signals.

**All data is synthetic and seeded.** Prices are simulated with a
geometric Brownian motion that has calm, normal, and stressed
volatility regimes; FX carry is a mean-reverting rate differential.
No real market data is used, and nothing here is a claim about any
real fund, strategy, or live return.

## Signals

- **Time-series momentum** (`signals.py`): sign of the trailing
  252-day return, scaled by its own history — the classic trend
  signal for futures and FX.
- **Moving-average crossover**: 50-day above 200-day average is long,
  otherwise short.
- **FX carry**: long the higher-yielding currency of the pair,
  position proportional to the rate differential.
- **Mean reversion**: fade short-term moves away from the 20-day
  average (a small sleeve, so the book is not all trend).

## Backtest and portfolio construction

- `backtest.py`: positions apply from the next day (no look-ahead),
  costs are charged per unit of turnover in basis points, and
  positions can be scaled to a 10% volatility target.
- `portfolio.py`: strategies are combined with equal-risk-contribution
  (risk-parity) weights from the covariance of strategy returns.
- Metrics reported per book: CAGR, annualised volatility, Sharpe,
  Sortino, maximum drawdown, and Calmar.

## Robust research procedures

- **Walk-forward validation** (`robustness.py`): the best momentum
  lookback is chosen in-sample for each fold and tested on the next
  fold out-of-sample, so overfitting shows up as an in-sample /
  out-of-sample Sharpe gap.
- **Cost sensitivity**: Sharpe at 0, 1, 2, 5, and 10 bps per trade.
- **Signal decay**: how fast the edge fades if execution is delayed
  1–10 days.
- **Simulated-vs-actual gap**: gross edge vs cost paid vs net return,
  with average daily turnover, so a researcher can see whether the
  idea survives realistic friction.

## How it differs from the other projects in this repo

- `cross-asset-model-validation-suite` and `model-validation-toolkit`
  validate pricing and risk models after the fact; this project builds
  and tests trading signals.
- `investment-model-governance-validator` reviews alpha/signal models
  from a second-line governance view (IC, VaR backtests, inventory);
  it never constructs a signal or runs a trading backtest.
- `vol-surface-consistency-checker` checks option volatility surfaces
  for arbitrage; `monte-carlo-xva-benchmark` prices XVA; neither is a
  systematic signal or portfolio research tool.
- `performance-measurement-engine` measures realised performance; this
  project researches signals before they trade.

## Run it

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m sys_signal_research --out research_report.json
PYTHONPATH=. python run_demo.py
```

## Files

- `sys_signal_research/data.py` — seeded synthetic futures/FX prices and carry
- `sys_signal_research/signals.py` — momentum, crossover, carry, mean reversion
- `sys_signal_research/backtest.py` — backtester, vol targeting, risk parity, metrics
- `sys_signal_research/portfolio.py` — combine strategy backtests into one book
- `sys_signal_research/robustness.py` — walk-forward, cost sensitivity, decay, gap
- `tests/` — 5 test modules
- `README.md`, `requirements.txt`, `.gitignore`, `run_demo.py`
