"""Metric computation: idempotent, incremental, with controlled backfills.

Computation is keyed by (run_id, metric, slice): re-running the same key
with the same inputs returns the stored result instead of recomputing, so
retries and duplicate queue deliveries cannot double-count. New data is
processed incrementally — only slices with new inputs are recomputed — and
a backfill replays a bounded slice range under an explicit backfill id so
it is visible as a backfill, not mistaken for a fresh measurement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class MetricResult:
    run_id: str
    metric_name: str
    metric_version: int
    slice_key: str
    value: float | None
    sample_size: int
    coverage: float  # fraction of expected scenarios with data, 0..1
    backfill_id: str | None = None


def aggregate(values: list[float], aggregation: str) -> float | None:
    if not values:
        return None
    if aggregation == "mean":
        return sum(values) / len(values)
    if aggregation == "count":
        return float(len(values))
    if aggregation == "max":
        return max(values)
    if aggregation == "rate":
        # values are 0/1 event indicators; rate = fraction of 1s
        return sum(values) / len(values)
    if aggregation == "p95":
        ordered = sorted(values)
        idx = math.ceil(0.95 * len(ordered)) - 1
        return ordered[max(0, idx)]
    raise ValueError(f"unknown aggregation {aggregation!r}")


class MetricComputer:
    def __init__(self):
        # (run_id, metric, slice) -> MetricResult
        self._results: dict[tuple[str, str, str], MetricResult] = {}
        # (run_id, metric, slice) -> fingerprint of the inputs, for idempotency
        self._fingerprints: dict[tuple[str, str, str], str] = {}

    def compute(self, run_id: str, metric_name: str, metric_version: int,
                slice_key: str, values: list[float], aggregation: str,
                expected_scenarios: int, backfill_id: str | None = None) -> MetricResult:
        key = (run_id, metric_name, slice_key)
        fingerprint = f"{aggregation}:{len(values)}:{sum(values)}:{expected_scenarios}"
        existing = self._results.get(key)
        if existing is not None and self._fingerprints.get(key) == fingerprint:
            return existing  # idempotent: same inputs, same result, no recompute
        coverage = (len(values) / expected_scenarios) if expected_scenarios > 0 else 0.0
        result = MetricResult(run_id, metric_name, metric_version, slice_key,
                              aggregate(values, aggregation), len(values),
                              round(min(1.0, coverage), 4), backfill_id)
        self._results[key] = result
        self._fingerprints[key] = fingerprint
        return result

    def backfill(self, run_id: str, metric_name: str, metric_version: int,
                 slices: dict[str, list[float]], aggregation: str,
                 expected_scenarios: int, backfill_id: str) -> list[MetricResult]:
        """Recompute a bounded set of slices, tagged with the backfill id."""
        return [self.compute(run_id, metric_name, metric_version, s, vals,
                             aggregation, expected_scenarios, backfill_id=backfill_id)
                for s, vals in slices.items()]

    def results_for_run(self, run_id: str) -> list[MetricResult]:
        return [r for (rid, _, _), r in self._results.items() if rid == run_id]

    def get(self, run_id: str, metric_name: str, slice_key: str) -> MetricResult | None:
        return self._results.get((run_id, metric_name, slice_key))
