"""Pipeline health / monitoring metrics.

Each stage (ingest, bronze checks, silver build, gold build) records its
row counts and wall-clock time. The summary turns those into the numbers a
pipeline owner watches: failure rate, late-arrival rate, and throughput.
Timings are measured, not asserted — they vary by machine, so tests check
the rates and counts, not the seconds.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class StageMetrics:
    name: str
    rows_in: int
    rows_out: int
    seconds: float

    @property
    def rows_per_second(self) -> float:
        if self.seconds <= 0:
            return float("inf")
        return self.rows_in / self.seconds

    @property
    def dropped(self) -> int:
        return self.rows_in - self.rows_out


@dataclass
class PipelineMetrics:
    stages: list[StageMetrics] = field(default_factory=list)
    bronze_rows: int = 0
    silver_rows: int = 0
    quarantine_rows: int = 0
    late_rows: int = 0
    gold_groups: int = 0

    def add_stage(self, name: str, rows_in: int, rows_out: int, seconds: float) -> None:
        self.stages.append(StageMetrics(name, rows_in, rows_out, seconds))

    @property
    def failure_rate(self) -> float:
        """Share of bronze rows quarantined."""
        if not self.bronze_rows:
            return 0.0
        return self.quarantine_rows / self.bronze_rows

    @property
    def late_rate(self) -> float:
        """Share of silver rows that arrived late."""
        if not self.silver_rows:
            return 0.0
        return self.late_rows / self.silver_rows

    @property
    def total_seconds(self) -> float:
        return sum(s.seconds for s in self.stages)

    def summary_lines(self) -> list[str]:
        lines = ["Pipeline health:"]
        for s in self.stages:
            lines.append(
                f"  {s.name}: {s.rows_in} in, {s.rows_out} out, "
                f"{s.seconds:.3f}s ({s.rows_per_second:,.0f} rows/s)"
            )
        lines.append(
            f"  failure rate: {self.failure_rate:.2%} "
            f"({self.quarantine_rows} of {self.bronze_rows} bronze rows quarantined)"
        )
        lines.append(
            f"  late-arrival rate: {self.late_rate:.2%} "
            f"({self.late_rows} of {self.silver_rows} silver rows late)"
        )
        lines.append(f"  gold groups: {self.gold_groups}")
        lines.append(f"  total pipeline time: {self.total_seconds:.3f}s")
        return lines


class StageTimer:
    """Context manager that times one pipeline stage."""

    def __init__(self, metrics: PipelineMetrics, name: str, rows_in: int):
        self.metrics = metrics
        self.name = name
        self.rows_in = rows_in
        self.rows_out = 0
        self._start = 0.0

    def __enter__(self) -> "StageTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.metrics.add_stage(
            self.name, self.rows_in, self.rows_out, time.perf_counter() - self._start
        )
