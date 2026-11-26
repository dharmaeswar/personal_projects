"""Tests for the Parquet columnar store."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from replay.ingest import generate_ticks, write_ticks_csv
from replay.store import compression_ratio, read_parquet, write_parquet


def test_parquet_round_trip(tmp_path):
    ticks = generate_ticks("ES", 1_000_000, 300, seed=4)
    path = str(tmp_path / "ticks.parquet")
    stats = write_parquet(path, ticks)
    assert stats["rows"] == 300
    assert stats["bytes"] > 0
    assert read_parquet(path) == ticks


def test_parquet_symbol_and_time_filters(tmp_path):
    ticks = generate_ticks("ES", 1_000_000, 100, seed=5)
    ticks += generate_ticks("NQ", 1_000_000, 100, seed=6)
    path = str(tmp_path / "ticks.parquet")
    write_parquet(path, ticks)
    es = read_parquet(path, symbol="ES")
    assert len(es) == 100 and all(t.symbol == "ES" for t in es)
    mid = ticks[50].ts_ns
    window = read_parquet(path, start_ns=mid, end_ns=mid)
    assert all(t.ts_ns == mid for t in window)


def test_parquet_smaller_than_csv(tmp_path):
    ticks = generate_ticks("ES", 1_000_000, 2_000, seed=11)
    csv_path = str(tmp_path / "ticks.csv")
    pq_path = str(tmp_path / "ticks.parquet")
    write_ticks_csv(csv_path, ticks)
    write_parquet(pq_path, ticks)
    ratio = compression_ratio(os.path.getsize(csv_path), os.path.getsize(pq_path))
    assert ratio > 1.0
