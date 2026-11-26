"""Tests for ingest: generation, CSV round-trip, validation."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from replay.ingest import Tick, generate_ticks, read_ticks_csv, write_ticks_csv


def test_generate_is_deterministic_and_ordered():
    a = generate_ticks("ES", 1_000_000, 200, seed=3)
    b = generate_ticks("ES", 1_000_000, 200, seed=3)
    assert a == b
    assert len(a) == 200
    assert all(a[i].ts_ns < a[i + 1].ts_ns for i in range(len(a) - 1))
    assert all(t.symbol == "ES" and t.price > 0 and t.size > 0 for t in a)


def test_generate_different_seeds_differ():
    a = generate_ticks("ES", 1_000_000, 50, seed=1)
    b = generate_ticks("ES", 1_000_000, 50, seed=2)
    assert a != b


def test_csv_round_trip(tmp_path):
    ticks = generate_ticks("NQ", 5_000_000, 100, seed=9)
    path = str(tmp_path / "ticks.csv")
    assert write_ticks_csv(path, ticks) == 100
    loaded = read_ticks_csv(path)
    assert loaded == ticks


def test_tick_rejects_bad_rows():
    with pytest.raises(ValueError):
        Tick.from_row(["1", "ES", "X", "100.0", "5"])
    with pytest.raises(ValueError):
        Tick.from_row(["1", "ES", "T", "-3.0", "5"])
    with pytest.raises(ValueError):
        Tick.from_row(["1", "ES", "T", "100.0"])
