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

## Equity factor risk (new, Nov 2026 — built for a JPMorgan Equity Portfolio Management / Model Risk Management role)

- `equity_factor_risk.py`: Axioma-style factor-risk analytics for an equity book.
  - `generate_equity_panel`: seeded synthetic panel of 40 stocks over 504 days, built from known
    Market / Size / Value / Momentum / Quality factor betas plus idiosyncratic noise.
  - `estimate_factor_betas`: OLS factor betas, alpha, R-squared and residual volatility per stock.
  - `tracking_error`: annualised volatility of active returns vs a benchmark.
  - `factor_risk_decomposition`: splits portfolio variance into factor risk and stock-specific risk,
    with each factor's risk contribution.
  - `portfolio_risk_summary`: one-page PM risk summary — total/factor/specific vol, tracking error,
    top factor tilts, concentration (Herfindahl), largest positions, sector exposures.
  - `governance_checks`: SR 11-7 style checks on the risk model itself — missing data, stale factors,
    low explanatory power, residual autocorrelation (Durbin-Watson), beta stability across halves,
    factor collinearity — each reported pass / warn / fail.
- The research report (`python -m sys_signal_research`) now includes an `equity_factor_risk` section
  with the equal-weighted book's vols, tracking error, top tilts and governance statuses.
- `tests/test_equity_factor_risk.py` — 9 tests: seeded reproducibility, beta recovery vs ground truth,
  tracking-error edge cases, variance additivity, summary completeness, governance pass on a clean
  panel and fail on a constant factor / gappy data.

## Cross-sectional equity alpha research (new, Nov 2026 — built for a Point72 Cubist Quantitative Researcher role)

- `equity_alpha.py`: the workflow a systematic-equities researcher runs on a new alpha idea — build the signal from point-in-time data only, measure its information coefficient, check how fast the edge decays with execution delay, and backtest a cost-aware long-short book.
  - `generate_equity_alpha_panel`: seeded synthetic panel of 40 stocks over 504 days. Returns are built from a known structure — a persistent drift tied to each stock's value and quality characteristics plus a stock-specific part, a market factor, and idiosyncratic noise — so the signals have a real (seeded) edge to discover. The drift is deliberately strong (about 22% annual cross-sectional dispersion) so a two-year, 40-stock panel can detect it; the point is to exercise the research tooling, not to claim a tradable edge.
  - Signals: 12-1 cross-sectional momentum (trailing return skipping the most recent month, z-scored each day), value (book-to-price) and quality (profitability) characteristics, plus an equal-weighted composite.
  - `information_coefficient`: daily rank IC vs forward returns, with mean IC, standard deviation, t-statistic and hit rate. On the seeded panel: momentum IC 0.042 (t = 4.3), value 0.049 (t = 6.6), quality 0.021 (t = 2.9), composite 0.052 (t = 7.7).
  - `signal_decay`: composite IC at 1/5/10/20-day lags — 0.052, 0.051, 0.050, 0.049. The edge is a persistent drift, so it decays slowly; a fast-fading signal would show up here as a collapse by lag 5.
  - `long_short_backtest`: daily long-short quintile book (top 20% long, bottom 20% short, equal-weighted, signal applied from the next day — no look-ahead), turnover charged at 5 bps. On the seeded panel: 46% CAGR, 7.3% annualised volatility, Sharpe 5.3, maximum drawdown −5.5%, mean daily turnover 4.5%. The high Sharpe is the seeded drift doing its job, not a market claim.
  - `alpha_report`: one-call summary of ICs, decay and backtest metrics.
- `tests/test_equity_alpha.py` — 11 tests: seeded reproducibility, cross-sectional standardisation, IC recovery vs the known drift, cost sensitivity (higher costs lower net returns; zero cost means net equals gross), dollar-neutral positions, and the full report.
- No real market data is used anywhere in this module, and nothing here claims a live return or any affiliation with Point72 or Cubist.

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
- `sys_signal_research/equity_factor_risk.py` — equity factor exposures, tracking error, risk summary, governance checks
- `sys_signal_research/signals.py` — momentum, crossover, carry, mean reversion
- `sys_signal_research/backtest.py` — backtester, vol targeting, risk parity, metrics
- `sys_signal_research/portfolio.py` — combine strategy backtests into one book
- `sys_signal_research/robustness.py` — walk-forward, cost sensitivity, decay, gap
- `tests/` — 6 test modules
- `README.md`, `requirements.txt`, `.gitignore`, `run_demo.py`
