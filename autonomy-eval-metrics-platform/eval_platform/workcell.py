"""Workcell / equipment performance simulation.

Simulates a robot workcell (pick-and-place cycles) with seeded randomness
and publishes effectiveness metrics through the eval platform, mirroring
the Amazon Robotics responsibility: simulate workcell or equipment
performance and publish metrics a program can monitor.

All data is synthetic. No real robots, workcells, or production numbers
are used, and nothing here describes a real Amazon system.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .provenance import EvalRun

# The three metrics this module publishes, with their aggregations.
WORKCELL_METRICS = (
    ("cycle_time_mean", "Mean workcell cycle time in seconds", "seconds",
     "mean", False),
    ("cycle_time_p95", "95th percentile workcell cycle time in seconds",
     "seconds", "p95", False),
    ("workcell_fault_rate", "Share of faulted workcell cycles", "rate",
     "rate", False),
)


@dataclass(frozen=True)
class WorkcellCycle:
    cycle_index: int
    cycle_time_s: float
    faulted: bool
    downtime_s: float = 0.0


def simulate_workcell_cycles(seed: int = 7, n_cycles: int = 500,
                             base_cycle_s: float = 12.0,
                             cycle_jitter_s: float = 1.5,
                             fault_rate: float = 0.02,
                             fault_downtime_s: float = 45.0
                             ) -> list[WorkcellCycle]:
    """Simulate n_cycles of a pick-and-place workcell.

    Cycle times are the base time plus uniform jitter; each cycle faults
    with probability fault_rate and adds a fixed downtime. Deterministic
    for a given seed, so a run can be replayed exactly.
    """
    if n_cycles <= 0:
        raise ValueError("n_cycles must be positive")
    if not 0.0 <= fault_rate <= 1.0:
        raise ValueError("fault_rate must be between 0 and 1")
    rng = random.Random(seed)
    cycles = []
    for i in range(n_cycles):
        faulted = rng.random() < fault_rate
        cycle_time = base_cycle_s + rng.uniform(-cycle_jitter_s,
                                                cycle_jitter_s)
        cycles.append(WorkcellCycle(
            i, round(cycle_time, 3), faulted,
            fault_downtime_s if faulted else 0.0))
    return cycles


def workcell_metrics(cycles: list[WorkcellCycle]) -> dict:
    """Effectiveness metrics for a list of simulated cycles.

    Returns mean and p95 cycle time, fault rate, throughput in cycles per
    hour (downtime included), and availability (productive time over total
    time). Empty input returns None values instead of raising.
    """
    if not cycles:
        return {"mean_cycle_s": None, "p95_cycle_s": None,
                "fault_rate": None, "throughput_per_hour": None,
                "availability": None}
    times = sorted(c.cycle_time_s for c in cycles)
    n = len(times)
    mean_cycle = sum(times) / n
    p95 = times[max(0, math.ceil(0.95 * n) - 1)]
    faults = sum(1 for c in cycles if c.faulted)
    total_time = sum(times) + sum(c.downtime_s for c in cycles)
    throughput = 3600.0 / (total_time / n) if total_time > 0 else None
    availability = sum(times) / total_time if total_time > 0 else None
    return {
        "mean_cycle_s": round(mean_cycle, 3),
        "p95_cycle_s": round(p95, 3),
        "fault_rate": round(faults / n, 4),
        "throughput_per_hour": round(throughput, 1) if throughput else None,
        "availability": round(availability, 4) if availability else None,
    }


def publish_workcell_metrics(platform, run_id: str,
                             cycles: list[WorkcellCycle],
                             slice_key: str = "workcell-1") -> dict:
    """Register the workcell metrics and compute them through the platform.

    Records one provenance-pinned run per metric (code, model, dataset,
    and scenario versions are pinned, as with eval runs), then computes
    each metric idempotently through the platform so retries cannot
    double-count. Returns {metric_name: MetricResult}.
    """
    times = [c.cycle_time_s for c in cycles]
    faults = [1.0 if c.faulted else 0.0 for c in cycles]
    values = {
        "cycle_time_mean": times,
        "cycle_time_p95": times,
        "workcell_fault_rate": faults,
    }
    results = {}
    for name, description, unit, aggregation, higher_is_better in WORKCELL_METRICS:
        definition = platform.registry.latest(name)
        if definition is None:
            definition = platform.register_metric(
                name, description, unit, aggregation,
                higher_is_better=higher_is_better)
        metric_run_id = f"{run_id}-{name}"
        platform.record_run(EvalRun(
            metric_run_id, name, definition.version, "code-wc1",
            "workcell-sim-2026.11", "workcell-scenarios-v3",
            "workcell-cycles-v1", "simulation"))
        results[name] = platform.compute_metric(
            metric_run_id, name, slice_key, values[name], len(cycles))
    return results
