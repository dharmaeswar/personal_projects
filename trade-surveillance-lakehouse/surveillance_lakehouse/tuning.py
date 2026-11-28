"""Query tuning: partitioned scan vs full scan.

Reads ``fact_trade`` two ways with pyarrow's dataset API and times
both, so the report shows the payoff of the lakehouse file layout in
numbers instead of asserting it:

- Partitioned: hive-partitioned Parquet, filter on the partition
  column (``trade_date``) plus a predicate on ``symbol`` — partition
  pruning skips the other dates' files, and the predicate is pushed
  down into the remaining files.
- Full scan: every partition file read and filtered in memory.

The layout guidance in the report (partition by trade_date, keep
files near 128 MB, sort by symbol inside a partition, Z-order on
account/symbol when a query filters both) is what a Trino/Iceberg
deployment would use; the timings here are measured locally with
pyarrow, not on a Trino cluster.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds


def write_partitioned_trades(silver_dir: Path) -> None:
    """Write a hive-partitioned copy of fact_trade for the tuning scan."""
    trades = pd.read_parquet(silver_dir / "fact_trade.parquet")
    instruments = pd.read_parquet(silver_dir / "dim_instrument.parquet")
    sym = dict(zip(instruments["instrument_key"], instruments["symbol"]))
    trades = trades.assign(symbol=trades["instrument_key"].map(sym))
    trades["trade_date"] = trades["trade_date"].astype(str)
    table = pa.Table.from_pandas(trades, preserve_index=False)
    hive = ds.partitioning(
        pa.schema([("trade_date", pa.string())]), flavor="hive")
    ds.write_dataset(table, str(silver_dir / "fact_trade_partitioned"),
                     format="parquet", partitioning=hive,
                     existing_data_behavior="overwrite_or_ignore")


def tune(silver_dir: Path, out_path: Path) -> dict:
    """Run both scans and write the tuning report. Returns the numbers."""
    dataset = ds.dataset(str(silver_dir / "fact_trade_partitioned"),
                         format="parquet", partitioning="hive")
    symbol, day = "AAPL", "2026-11-18"

    t0 = time.perf_counter()
    part = dataset.to_table(
        filter=(ds.field("trade_date") == day)
        & (ds.field("symbol") == symbol))
    part_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    full = dataset.to_table()
    mask = pc.and_(pc.equal(full.column("trade_date"), day),
                   pc.equal(full.column("symbol"), symbol))
    full = full.filter(mask)
    full_ms = (time.perf_counter() - t0) * 1000

    result = {
        "symbol": symbol, "trade_date": day,
        "partitioned_rows": part.num_rows,
        "partitioned_ms": round(part_ms, 2),
        "full_scan_rows": full.num_rows,
        "full_scan_ms": round(full_ms, 2),
        "speedup": round(full_ms / part_ms, 2) if part_ms else None,
        "total_rows": dataset.count_rows(),
    }
    lines = [
        "# Query tuning — fact_trade",
        "",
        f"Query: all {symbol} trades on {day}.",
        "",
        f"- Partitioned scan (partition pruning + predicate pushdown): "
        f"{result['partitioned_rows']} rows in {result['partitioned_ms']} ms",
        f"- Full scan (read all {result['total_rows']} rows, filter in memory): "
        f"{result['full_scan_rows']} rows in {result['full_scan_ms']} ms",
        f"- Speedup: {result['speedup']}x",
        "",
        "## File-layout guidance (for the Trino / Iceberg deployment)",
        "",
        "- Partition by trade_date: every surveillance query is date-scoped, "
        "so pruning removes whole days of files before any row is read.",
        "- Keep files near 128 MB: many tiny files cost more in planning "
        "and S3 calls than they save in scan time.",
        "- Sort by symbol inside each partition: a symbol predicate then "
        "skips row groups as well as files.",
        "- Z-order on (account_id, symbol) when a query filters both, "
        "so the CAT and wash-trade queries share the same layout.",
        "",
        "Measured locally with pyarrow, not on a Trino cluster; the "
        "speedup here is small because the demo is 1,500 rows. The "
        "mechanism (pruning + pushdown) is the same at billions of rows.",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    return result
