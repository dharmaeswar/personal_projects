# Regulatory Trade-Pattern Analytics

Market-regulation analytics toolkit: loads order, trade and position
data into a SQLite warehouse, runs statistical triage and rule-based
trade-pattern detectors, and writes a regulatory review report with
findings, CSV exports and a findings chart.

Built for a Sr. Regulatory Data Scientist role at an exchange: the
work mirrors analysing order, trade and position data from Market
Regulation data warehouses, building working solutions that augment
analytical capability, and producing regulatory data-analysis reports.
It also fits a Senior SQL / Data Analytics Developer role for NYSE
trading data (ICE, Nov 2026): SQL design and optimisation, query-plan
review, automated data collection, statistical analysis and reporting
on large-scale trading data.

## What it does

- **Warehouse** (`trade_reg_analytics/data.py`): seeded synthetic
  order/trade/position data (6 instruments, 40 accounts, 20 business
  days) loaded into SQLite with plain SQL — relational tables for
  orders, trades and net positions.
- **Statistics** (`trade_reg_analytics/stats.py`): daily volume,
  rolling z-scores, outlier-day flags, account volume share and
  close-to-close return stats.
- **Detectors** (`trade_reg_analytics/patterns.py`): wash trades
  (matched buy/sell, same account/day), spoofing/layering (large
  orders cancelled within 10 seconds), marking the close (late trades
  priced away from VWAP), position concentration (>= 35% of net open
  interest). Every finding cites the orders behind it with a severity
  score and a plain-language reason.
- **Query tuning** (`trade_reg_analytics/tuning.py`): EXPLAIN QUERY
  PLAN review, wall-clock timing and index recommendations for the
  five recurring analytics queries. Run with `--tune`; it writes
  `tuning_report.md` and `tuning_summary.json` next to the report.
- **Microstructure** (`trade_reg_analytics/microstructure.py`): per
  instrument-day VWAP, trade-price deviation from VWAP (an
  effective-spread proxy in basis points), buy/sell imbalance,
  intraday price dispersion and large-trade share, with plain-language
  flags for days the tape itself says are unusual.
- **Reporting** (`trade_reg_analytics/report.py`): Markdown report,
  `findings.csv`, `daily_volume.csv`, `summary.json` and an SVG bar
  chart of findings by pattern.

## Demo result (seed 42, 20 days)

- Warehouse: 19,755 orders, 17,177 trades, 4,643 position rows
- Findings: 20 wash-trade flags (ACC-007, one per day) and 20
  spoofing flags (ACC-019, one per day) — both planted patterns are
  found on every day; no false concentration or close-marking flags
  on this seed. The planted patterns are the test signal, not real
  market abuse: all data is synthetic.

## Market microstructure (seed 42, 20 days)

120 instrument-days: median mean absolute deviation from VWAP 4.04
bps, median absolute buy/sell imbalance 0.07, median large-trade
share 0.36. 13 days flagged (max deviation >= 25 bps or |imbalance|
>= 0.25) — ordinary days peak at 10-17 bps from VWAP, while flagged
days run 31-90 bps; the largest, 90.3 bps on ES 2026-11-16, is a
planted close-marking trade priced away from VWAP. Thresholds are
parameters in `flag_microstructure_days`, not hard-coded facts.

## Query tuning (seed 42, 20 days, `--tune`)

Five recurring analytics queries, measured before and after the
recommended indexes (median of 3–5 runs, SQLite, demo scale):

| Query | Before | After | Speedup |
|---|---|---|---|
| Daily volume by instrument | 8.38 ms, full scan | 3.95 ms, index seek | 2.12x |
| Account volume share (one day) | 1.24 ms, full scan | 0.39 ms, index seek | 3.15x |
| Wash-trade candidates (self-join) | 2.82 ms, full scan | 0.54 ms, index seek | 5.26x |
| Fast-cancel scan (spoofing triage) | 2.34 ms, full scan | 0.74 ms, index seek | 3.14x |
| Position concentration (one day) | 0.49 ms, full scan | 0.24 ms, index seek | 2.05x |

All five full-table scans are removed. The wash-trade self-join
needed a second pass: the first index choice made the planner pick a
date-led index and run slower (0.21x), so a composite index on
(account, instrument, trade_date, side, quantity) was added and the
query then ran 5.26x faster. Timings are demo-scale (17k trades),
not production benchmarks.

## Run it

```bash
pip install -r requirements.txt
pytest -q
python -m trade_reg_analytics --db warehouse.db --out report
python -m trade_reg_analytics --db warehouse.db --out report --tune
python run_demo.py
```

## Files

- `trade_reg_analytics/data.py`, `stats.py`, `patterns.py`,
  `tuning.py`, `microstructure.py`, `report.py`, `__main__.py`
- `tests/` — 6 test modules, 36 tests
- `README.md`, `requirements.txt`, `run_demo.py`
