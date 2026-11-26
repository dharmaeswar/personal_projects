# Research Event Replay Framework

A research-technology toolkit for quant researchers: ingest raw exchange
tick data, store it in a columnar Parquet layout, replay it deterministically
through a simulation loop, slice and backtest it from Python, and schedule
the heavy jobs on a Slurm-style cluster queue.

Built as the role project for the DRW Software Engineer, Research Technology
application (high-throughput event-stream ingest, distributed HPC compute,
Python + C++ research tooling, Parquet/Arrow columnar data).

**All market data is synthetic and seeded.** No real exchange data, no real
trading, and no claim about any real firm, fund, or strategy is involved.

## What it does

| Module | What it mirrors | Behaviour |
|---|---|---|
| `replay/ingest.py` | Raw exchange data ingest | Seeded deterministic tick streams (trade/quote events, ns timestamps); CSV read/write with strict row validation |
| `replay/store.py` | Columnar data platform | Parquet with dictionary-encoded symbol/side columns and Snappy compression; symbol and time-range reads; measured compression ratio vs CSV |
| `replay/replay.py` | Simulation / replay loop | Merges many symbol streams into one strictly time-ordered event stream; deterministic tie-breaking; time-window slicing; trade-bar aggregation |
| `replay/backtest.py` | Research tooling | Momentum signal over bar closes, no-lookahead backtest, total return / Sharpe / max drawdown |
| `replay/scheduler.py` | HPC job scheduling (Slurm-style) | FIFO queue, CPU/memory accounting, jobs wait when the cluster is full, bounded retries on failure |
| `cpp/ingest_core.cpp` | Throughput-critical C++17 core | Allocation-light parse loop over raw tick CSVs; per-symbol counts, volume, min/max price; bad rows counted, never silently dropped |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python run_demo.py
```

Demo run (10,000 synthetic ticks, 2 symbols): CSV + Parquet written,
Parquet read back, 10,000 events replayed in order, one-millisecond bars built,
momentum backtest run, one Slurm-style job scheduled and completed.

## Design notes

- **Determinism:** the replay engine merges streams with a heap keyed on
  (timestamp, stream order), so the same input always replays in the same
  order. A researcher can reproduce a run exactly.
- **Columnar storage:** symbols and sides are dictionary-encoded and the
  file is Snappy-compressed; the demo measures the real compression ratio
  against the raw CSV instead of claiming one.
- **No look-ahead:** the backtest only ever trades the return *after* the
  bar that produced the signal.
- **Scheduling:** jobs larger than the cluster are rejected at submit time;
  a failed job retries up to its `max_retries`, then fails for real.
- **C++ core:** compiled and exercised by `tests/test_cpp.py` (skipped
  automatically when no C++ compiler is present); bad rows make the
  program exit non-zero instead of being silently skipped.
