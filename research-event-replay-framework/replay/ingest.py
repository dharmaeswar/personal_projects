"""Synthetic exchange tick ingest.

Generates seeded, deterministic tick streams that stand in for raw exchange
data (trade and quote events), and reads/writes the plain-text tick files
the fast C++ ingest core consumes. Nothing here touches a real feed.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Tick:
    """One exchange event: nanosecond timestamp, symbol, side, price, size."""

    ts_ns: int
    symbol: str
    side: str  # "B" (bid), "A" (ask), "T" (trade)
    price: float
    size: int

    def to_row(self) -> list:
        return [self.ts_ns, self.symbol, self.side, f"{self.price:.4f}", self.size]

    @classmethod
    def from_row(cls, row: list) -> "Tick":
        if len(row) != 5:
            raise ValueError(f"tick row must have 5 fields, got {len(row)}: {row!r}")
        ts_ns = int(row[0])
        symbol = row[1].strip()
        side = row[2].strip().upper()
        if side not in ("B", "A", "T"):
            raise ValueError(f"bad side {side!r} in row {row!r}")
        price = float(row[3])
        size = int(row[4])
        if price <= 0 or size <= 0 or ts_ns < 0:
            raise ValueError(f"non-positive tick field in row {row!r}")
        return cls(ts_ns, symbol, side, price, size)


def generate_ticks(
    symbol: str,
    start_ns: int,
    count: int,
    seed: int = 42,
    start_price: float = 100.0,
) -> list[Tick]:
    """Generate ``count`` deterministic synthetic ticks for one symbol.

    Prices follow a small random walk; timestamps advance by a random
    1-50 microsecond gap, so the stream is strictly time-ordered.
    """
    rng = random.Random(seed)
    ticks: list[Tick] = []
    ts = start_ns
    price = start_price
    for _ in range(count):
        ts += rng.randint(1_000, 50_000)  # 1-50 microseconds
        price *= math.exp(rng.gauss(0.0, 0.0004))
        price = max(price, 0.01)
        side = rng.choice(["B", "A", "T"])
        size = rng.choice([1, 5, 10, 25, 100])
        ticks.append(Tick(ts, symbol, side, round(price, 4), size))
    return ticks


def write_ticks_csv(path: str, ticks: list[Tick]) -> int:
    """Write ticks to a CSV file with a header. Returns rows written."""
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts_ns", "symbol", "side", "price", "size"])
        for tick in ticks:
            writer.writerow(tick.to_row())
    return len(ticks)


def read_ticks_csv(path: str) -> list[Tick]:
    """Read ticks from a CSV file, skipping the header. Raises on bad rows."""
    ticks: list[Tick] = []
    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header != ["ts_ns", "symbol", "side", "price", "size"]:
            raise ValueError(f"unexpected tick CSV header: {header!r}")
        for row in reader:
            if not row:
                continue
            ticks.append(Tick.from_row(row))
    return ticks
