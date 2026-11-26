"""Columnar Parquet store for tick data.

Ticks land in Parquet files partitioned by symbol, with the schema a
research platform needs: nanosecond timestamps, dictionary-encoded
symbols, and Snappy compression. Read paths cover full scans, symbol
slices, and time-range slices, and report the compression the columnar
layout actually achieves.
"""

from __future__ import annotations

import os

import pyarrow as pa
import pyarrow.parquet as pq

from .ingest import Tick

SCHEMA = pa.schema(
    [
        pa.field("ts_ns", pa.int64(), nullable=False),
        pa.field("symbol", pa.dictionary(pa.int32(), pa.string()), nullable=False),
        pa.field("side", pa.dictionary(pa.int32(), pa.string()), nullable=False),
        pa.field("price", pa.float64(), nullable=False),
        pa.field("size", pa.int32(), nullable=False),
    ]
)


def ticks_to_table(ticks: list[Tick]) -> pa.Table:
    """Convert ticks to an Arrow table matching SCHEMA."""
    return pa.Table.from_pylist(
        [
            {
                "ts_ns": t.ts_ns,
                "symbol": t.symbol,
                "side": t.side,
                "price": t.price,
                "size": t.size,
            }
            for t in ticks
        ],
        schema=SCHEMA,
    )


def table_to_ticks(table: pa.Table) -> list[Tick]:
    """Convert an Arrow table back to Tick objects, in stored order."""
    rows = table.to_pylist()
    return [
        Tick(int(r["ts_ns"]), r["symbol"], r["side"], float(r["price"]), int(r["size"]))
        for r in rows
    ]


def write_parquet(path: str, ticks: list[Tick], compression: str = "snappy") -> dict:
    """Write ticks to a Parquet file. Returns write stats (rows, bytes)."""
    table = ticks_to_table(ticks)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pq.write_table(table, path, compression=compression)
    return {"rows": len(ticks), "bytes": os.path.getsize(path), "compression": compression}


def read_parquet(
    path: str,
    symbol: str | None = None,
    start_ns: int | None = None,
    end_ns: int | None = None,
) -> list[Tick]:
    """Read ticks back, optionally filtered by symbol and time range."""
    table = pq.read_table(path)
    ticks = table_to_ticks(table)
    out = []
    for t in ticks:
        if symbol is not None and t.symbol != symbol:
            continue
        if start_ns is not None and t.ts_ns < start_ns:
            continue
        if end_ns is not None and t.ts_ns > end_ns:
            continue
        out.append(t)
    return out


def compression_ratio(csv_bytes: int, parquet_bytes: int) -> float:
    """How many times smaller the Parquet file is than the raw CSV."""
    if parquet_bytes <= 0:
        raise ValueError("parquet size must be positive")
    return csv_bytes / parquet_bytes
