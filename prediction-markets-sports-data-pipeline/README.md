# Prediction Markets — Sports Data Pipeline

A Python data pipeline for a prediction-markets / sports-analytics desk:
ingest multi-book sports and geopolitical odds, cleanse them into
research-ready probabilities, store them in a partitioned columnar layout,
and turn them into the packaged reports and backtests researchers hand to
traders.

Built as the role project for the Susquehanna (SIG) — Data Engineer |
Python | Predictions application (Job 10347): Python data stack
(NumPy/pandas), data pipelines for quant research and trading, numeric
data storage, large and varied datasets, performance-tuned processing,
Kafka / Kubernetes / cloud as desired skills.

**All data is synthetic and seeded.** No real odds, prices, events, or
outcomes are used, and nothing here is a claim about any real book,
market, or result.

## What it does

| Module | What it mirrors | Behaviour |
|---|---|---|
| `ingest.py` | Multi-book odds feed | 12 seeded events (8 sports, 4 geopolitical) x 3 books, 5-minute snapshots; deliberate defects (2 missing odds, 1 stale timestamp, 2 duplicates) so cleansing has real work to do |
| `stream.py` | Kafka topic | In-process append-only log with offsets, offset-committing consumer, replay with key dedupe (at-least-once delivery, exactly-once effect) |
| `cleanse.py` | Data quality / cleansing | Dedupe, quarantine missing odds and stale quotes, American odds → implied probability, overround (vig) removal so fair probs sum to 1 |
| `store.py` | Numeric data storage | Partitioned columnar `.npz` store (one array per column, one partition per event/date) + manifest; point-in-time `read_asof` so a backtest never sees the future |
| `signals.py` | Research signals | Cross-book consensus probabilities, market-movement detection, model-vs-market edge, flat-stake no-look-ahead backtest |
| `reports.py` | Packaged reports | JSON + plain-text daily research report: data quality, top movers, top edges, backtest |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python run_demo.py
```

Demo writes `demo_out/`: `raw_feed.csv`, the partitioned store, and
`report.json` / `report.txt`.

## Demo run (seed 7, 2026-11-28)

- Feed: 866 snapshot rows (12 events x 24 snapshots x 3 books, +2 dupes)
- Streamed: 864 unique rows delivered (2 exact duplicates deduped by key)
- Cleansed: 861 kept; 3 quarantined at cleanse (2 missing odds, 1 stale)
  — 5 defective rows in total across stream dedupe + cleanse
- Store: 12 partitions (one per event)
- Backtest (flat $100 stakes, 5% edge threshold): 12 bets, +$642.00
  profit on $1,200 staked (ROI 53.5%, hit rate 66.7% — 4 seeded upsets lose)

## Honest limits

- Data is synthetic and seeded; no live odds feed is connected.
- The stream is an in-process simulation of Kafka semantics — no real
  Kafka broker, and no Kubernetes deployment, is involved. The resume
  does not claim Kafka or Kubernetes production experience.
- The columnar store uses NumPy `.npz` (one array per column) as a
  dependency-light stand-in; Parquet/Iceberg is the stated production
  target, not a runtime used here.
- The "research model" probabilities are seeded inputs to the demo, not
  a fitted model; the backtest measures the pipeline, not a live edge.
- Performance is measured on the seeded feed only; no production-scale
  latency or throughput claim is made.

## Tests

`python -m pytest tests/ -q` — 20 tests: odds conversion and round-trip,
feed determinism, cleanse quarantine counts, store round-trip and
point-in-time reads, consensus/movement math, backtest threshold and
determinism, stream delivery, dedupe, and replay.
