"""End-to-end demo: generate ticks, store as Parquet, replay, backtest."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from replay.backtest import backtest_ticks
from replay.ingest import generate_ticks, read_ticks_csv, write_ticks_csv
from replay.replay import ReplayEngine, to_bars
from replay.scheduler import Cluster, Scheduler
from replay.store import compression_ratio, read_parquet, write_parquet


def main() -> None:
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_out")
    os.makedirs(out, exist_ok=True)

    ticks_a = generate_ticks("ES", 1_700_000_000_000_000_000, 5_000, seed=7)
    ticks_b = generate_ticks("NQ", 1_700_000_000_000_000_000, 5_000, seed=8)
    csv_path = os.path.join(out, "ticks.csv")
    write_ticks_csv(csv_path, ticks_a + ticks_b)
    print(f"wrote {len(ticks_a) + len(ticks_b)} ticks to {csv_path}")

    pq_path = os.path.join(out, "ticks.parquet")
    stats = write_parquet(pq_path, ticks_a + ticks_b)
    ratio = compression_ratio(os.path.getsize(csv_path), stats["bytes"])
    print(f"parquet: {stats['rows']} rows, {stats['bytes']} bytes, "
          f"{ratio:.2f}x smaller than CSV")

    loaded = read_parquet(pq_path, symbol="ES")
    print(f"read back {len(loaded)} ES ticks from Parquet")

    seen: list = []
    engine = ReplayEngine([ticks_a, ticks_b])
    run_stats = engine.run([lambda t, i: seen.append(t)])
    print(f"replayed {run_stats['events']} events in order, "
          f"max gap {run_stats['max_gap_ns']} ns")

    bars = to_bars(read_ticks_csv(csv_path), bar_ns=1_000_000)
    print(f"built {len(bars)} one-millisecond bars from trade ticks")
    result = backtest_ticks(read_ticks_csv(csv_path), 1_000_000, lookback=5)
    print(f"backtest: {result['trades']} trades, total return "
          f"{result['total_return']:.4f}, Sharpe {result['sharpe']:.2f}, "
          f"max drawdown {result['max_drawdown']:.4f}")

    sched = Scheduler(Cluster(total_cpus=8, total_mem_gb=32))
    job = sched.submit("nightly-replay", cpus=4, mem_gb=16,
                       command="python run_replay.py")
    started = sched.schedule()
    print(f"scheduler started {len(started)} job(s): {[j.name for j in started]}")
    sched.finish(job, success=True)
    print(f"scheduler status: {sched.status()}")


if __name__ == "__main__":
    main()
