"""Backpressure, bottleneck triangulation, and cost/throughput modelling.

The Zscaler Data & APIs role asks for performance analysis, bottleneck
triangulation (producer / broker / consumer / stateful operator),
backpressure tuning, and cost/throughput optimization at TB+/day scale.
This module implements the analysis half on stage metrics supplied by
the caller — it does not run a real Kafka/Flink cluster:

- Triangulation: given per-stage input/output rates and queue depths,
  name the bottleneck stage (the one whose output lags its input most
  while its queue grows).
- Backpressure controller: given consumer lag and queue depth, recommend
  an action — scale consumers, add partitions, or shed load — with the
  reason attached, so the recommendation is auditable.
- Cost model: a planning model for cost per TB/day at a given throughput
  (illustrative constants, stated in the code — not a cloud bill).
"""

from __future__ import annotations

from dataclasses import dataclass

# Illustrative planning constants for the cost model (USD). These are
# not measured cloud prices; they let the demo show the shape of the
# cost/throughput trade-off: retention dominates at low throughput,
# compute dominates as throughput grows.
COST_PER_TB_INGEST = 42.0
COST_PER_TB_RETAINED_DAY = 9.0
COST_PER_TB_SCANNED = 5.0


@dataclass
class StageMetrics:
    """One pipeline stage's observed rates over a measurement window."""

    stage: str  # producer | broker | consumer | stateful-operator
    input_per_sec: float
    output_per_sec: float
    queue_depth: int
    capacity_per_sec: float

    def utilization(self) -> float:
        if self.capacity_per_sec <= 0:
            return 0.0
        return self.input_per_sec / self.capacity_per_sec

    def drain_ratio(self) -> float:
        """Output / input. Below 1.0 the stage is falling behind."""
        if self.input_per_sec <= 0:
            return 1.0
        return self.output_per_sec / self.input_per_sec


def triangulate(stages: list[StageMetrics]) -> dict:
    """Name the bottleneck stage and explain why.

    The bottleneck is the stage with the lowest drain ratio; ties break
    on the deepest queue. Returns the stage, its drain ratio, and the
    evidence for the call.
    """
    if not stages:
        raise ValueError("at least one stage is required")
    ranked = sorted(stages,
                    key=lambda s: (s.drain_ratio(), -s.queue_depth))
    worst = ranked[0]
    return {
        "bottleneck": worst.stage,
        "drain_ratio": round(worst.drain_ratio(), 3),
        "utilization": round(worst.utilization(), 3),
        "queue_depth": worst.queue_depth,
        "evidence": (
            f"{worst.stage} drains {worst.output_per_sec:.0f}/s of "
            f"{worst.input_per_sec:.0f}/s in ({worst.drain_ratio():.2f}x) "
            f"with queue depth {worst.queue_depth} at "
            f"{worst.utilization():.0%} of capacity"
        ),
        "ranking": [s.stage for s in ranked],
    }


@dataclass
class BackpressureController:
    """Recommend an action from consumer lag and queue depth."""

    lag_records: int = 100_000
    queue_high: int = 50_000
    lag_high: int = 1_000_000

    def recommend(self, lag: int, queue_depth: int,
                  consumer_utilization: float) -> dict:
        """Return an action + reason. Never silently drops data."""
        if lag >= self.lag_high or queue_depth >= self.queue_high:
            return {
                "action": "shed_load",
                "reason": (
                    f"lag {lag} records / queue {queue_depth} exceed "
                    f"safe bounds ({self.lag_high} / {self.queue_high}); "
                    "apply backpressure to producers and shed "
                    "lowest-priority traffic first"),
            }
        if lag >= self.lag_records:
            if consumer_utilization >= 0.9:
                return {
                    "action": "scale_consumers",
                    "reason": (
                        f"lag {lag} with consumers at "
                        f"{consumer_utilization:.0%} utilization — "
                        "add consumer parallelism before tuning"),
                }
            return {
                "action": "tune_consumer",
                "reason": (
                    f"lag {lag} but consumers at "
                    f"{consumer_utilization:.0%} utilization — "
                    "raise batch size / poll timeout before scaling"),
            }
        return {
            "action": "none",
            "reason": f"lag {lag} within bounds; no action needed",
        }


def cost_for_throughput(tb_per_day: float, *, retention_days: int = 7,
                        scan_ratio: float = 0.2) -> dict:
    """Planning cost for a streaming pipeline at a given throughput.

    Returns the daily cost split (ingest / retention / scan) so the
    caller can see which part dominates at TB+/day scale.
    """
    if tb_per_day < 0:
        raise ValueError("tb_per_day must be >= 0")
    ingest = tb_per_day * COST_PER_TB_INGEST
    retention = tb_per_day * retention_days * COST_PER_TB_RETAINED_DAY
    scan = tb_per_day * scan_ratio * COST_PER_TB_SCANNED
    total = ingest + retention + scan
    return {
        "tb_per_day": tb_per_day,
        "ingest_usd_per_day": round(ingest, 2),
        "retention_usd_per_day": round(retention, 2),
        "scan_usd_per_day": round(scan, 2),
        "total_usd_per_day": round(total, 2),
        "dominant": max(
            (("ingest", ingest), ("retention", retention), ("scan", scan)),
            key=lambda item: item[1])[0],
    }
