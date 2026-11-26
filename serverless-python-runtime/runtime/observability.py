"""Observability: per-invocation metrics and structured JSON logs.

Every invocation the executor runs is recorded here: total count, cold vs
warm, failures, and latency percentiles. Logs are single-line JSON objects
so a log pipeline can parse them without guessing at formats. Nothing here
touches the network; the runtime owner decides where metrics and logs go.
"""

import json
import sys
import time
from contextlib import contextmanager


def percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile; 0.0 when there are no samples."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(1, int(-(-pct * len(ordered) // 100)))
    return ordered[min(rank, len(ordered)) - 1]


class Metrics:
    """Counters and latency samples for one runtime."""

    def __init__(self):
        self.total = 0
        self.cold_starts = 0
        self.failures = 0
        self.latencies_ms: list[float] = []

    def record(self, total_ms: float, cold: bool, ok: bool) -> None:
        self.total += 1
        self.cold_starts += 1 if cold else 0
        self.failures += 0 if ok else 1
        self.latencies_ms.append(float(total_ms))

    def summary(self) -> dict:
        return {
            "invocations": self.total,
            "cold_starts": self.cold_starts,
            "warm_invocations": self.total - self.cold_starts,
            "failures": self.failures,
            "p50_ms": round(percentile(self.latencies_ms, 50), 3),
            "p95_ms": round(percentile(self.latencies_ms, 95), 3),
            "max_ms": round(max(self.latencies_ms), 3)
            if self.latencies_ms
            else 0.0,
        }


def log_event(level: str, message: str, **fields) -> str:
    """Write one JSON-lines log record to stdout; return the line."""
    record = {"level": level, "message": message, **fields}
    line = json.dumps(record)
    print(line, file=sys.stdout, flush=True)
    return line


@contextmanager
def span(name: str):
    """Time a named operation and yield a dict that gains duration_ms."""
    started = time.perf_counter()
    info: dict = {"name": name}
    try:
        yield info
    finally:
        info["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
