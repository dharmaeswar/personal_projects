# Regulatory Trade-Pattern Analytics

Market-regulation analytics toolkit: loads order, trade and position
data into a SQLite warehouse, runs statistical triage and rule-based
trade-pattern detectors, and writes a regulatory review report with
findings, CSV exports and a findings chart.

Built for a Sr. Regulatory Data Scientist role at an exchange: the
work mirrors analysing order, trade and position data from Market
Regulation data warehouses, building working solutions that augment
analytical capability, and producing regulatory data-analysis reports.

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

## Run it

```bash
pip install -r requirements.txt
pytest -q
python -m trade_reg_analytics --db warehouse.db --out report
python run_demo.py
```

## Files

- `trade_reg_analytics/data.py`, `stats.py`, `patterns.py`,
  `report.py`, `__main__.py`
- `tests/` — 4 test modules, 23 tests
- `README.md`, `requirements.txt`, `run_demo.py`
