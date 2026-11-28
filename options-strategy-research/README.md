# Options Strategy Research

Research tooling for a systematic options trading team: acquire option
data, rebuild the volatility surface, check it for arbitrage, simulate
option strategies, and backtest a delta-hedged straddle the way a
research engineer would with a quantitative researcher — implement the
study, simulate the strategy, and hand the desk numbers it can trust.

Built as the role project for the DRW — Research Engineer (Options)
application (Greenwich, CT): systematic trading team, research studies,
strategy simulation, data acquisition / storage / visualisation, Python,
quantitative finance, Linux large-scale systems.

**All data is synthetic and seeded.** The underlying follows a seeded
geometric Brownian motion and option quotes are priced off a Black-Scholes
smile. No real market data is used, and nothing here is a claim about
any real firm, strategy, or return.

## What it does

1. **Data acquisition and storage** (`options/data.py`): simulates a
   252-day underlying path (seeded GBM) and builds an option chain —
   3 expiries (30/60/90 days) x 7 strikes x calls/puts — with bid/ask
   around a Black-Scholes mid. Both are written to disk
   (`demo_out/prices.json`, `demo_out/chain.csv`) and read back, so the
   pipeline consumes stored data exactly like a feed dump.
2. **Volatility surface** (`options/surface.py`): rebuilds implied vols
   by bisection, then runs the no-arbitrage checks a model-validation
   reviewer runs — call prices fall with strike, butterfly spreads are
   non-negative, total variance does not fall with expiry. The clean
   synthetic chain passes all three; the tests break each one on
   purpose and confirm the check fires.
3. **Strategy simulation** (`options/strategies.py`): expiry payoffs
   for a long ATM straddle, a covered call, and an iron condor,
   including breakevens and max gain/loss, plus an ASCII payoff diagram.
4. **Backtest** (`options/backtest.py`): daily delta-hedged long
   straddle over the price path — buy the ATM straddle, re-hedge delta
   every day with the underlying, close at expiry. Positions use only
   prices known up to the current day (no look-ahead); each hedge trade
   pays a per-trade cost. Reports total P&L, Sharpe, and max drawdown
   per trade, and aggregates a study of non-overlapping 30-day windows.
5. **Visualisation** (`options/visualize.py`): ASCII payoff diagrams
   and a daily P&L series exported as CSV.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
python3 run_demo.py            # writes demo_out/report.txt, chain.csv, prices.json, pnl.csv
python3 -m pytest tests/ -q    # 28 tests
```

## Demo output (seed 42)

- Underlying: 252 days, last close 152.71; chain: 42 quotes.
- Surface: 3 expiries; arbitrage breaks found: 0.
- Delta-hedged straddle study: 8 non-overlapping 30-day trades, 5 wins,
  total P&L +6.37, average Sharpe 0.92, worst drawdown -1.62; see
  `demo_out/report.txt` for per-trade P&L, Sharpe, and max drawdown.

## Honest limits

- Synthetic seeded data only; not a live feed, not a production system.
- Black-Scholes with constant rates and no dividends; the smile is a
  fixed quadratic, not fitted to market quotes.
- The backtest reprices options at the same constant vol every day, so
  it measures realised-vs-implied vol (gamma/theta) only — it does not
  model vol-surface moves, jumps, or liquidity.
- No C/C++ code: the posting lists low-level languages as a plus, and
  the author has no verified C/C++ production work, so none is claimed.
- Single-threaded, standard-library only; the large-scale, concurrent,
  low-latency systems in the posting are not reproduced at demo scale.
