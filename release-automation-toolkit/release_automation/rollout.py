"""Canary rollout simulator with health gates.

A release rolls out in stages (default 5% -> 25% -> 50% -> 100% of
traffic). After each stage the health gate compares the stage's
observed metrics against thresholds: error rate, p95 latency, and
success rate. A stage that breaches any threshold triggers an
automatic rollback to the previous version and stops the rollout;
a stage inside all thresholds promotes to the next one.

The simulator takes the observed metrics as input (a list of metric
snapshots, one per stage). It does not collect metrics itself — in a
real system these would come from the monitoring stack; here the
caller supplies them so the promote / roll-back logic is testable
and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_STAGES = (5, 25, 50, 100)


@dataclass
class HealthThresholds:
    """Breaches are: error rate above max, p95 latency above max,
    or success rate below min."""

    max_error_rate: float = 0.01  # 1% of requests erroring
    max_p95_latency_ms: float = 500.0
    min_success_rate: float = 0.99


@dataclass
class StageMetrics:
    """Observed health for one canary stage."""

    error_rate: float
    p95_latency_ms: float
    success_rate: float


@dataclass
class StageResult:
    stage_percent: int
    metrics: StageMetrics
    promoted: bool
    breaches: list[str] = field(default_factory=list)


@dataclass
class RolloutResult:
    service: str
    version: str
    previous_version: str
    completed: bool  # True only if the rollout reached 100%
    rolled_back: bool
    stages: list[StageResult] = field(default_factory=list)
    rollback_events: list[str] = field(default_factory=list)

    @property
    def stages_completed(self) -> int:
        return len(self.stages)

    @property
    def final_traffic_percent(self) -> int:
        """Traffic on the new version when the rollout stopped."""
        if self.rolled_back:
            return 0
        if not self.stages:
            return 0
        return self.stages[-1].stage_percent


def check_health(metrics: StageMetrics, thresholds: HealthThresholds) -> list[str]:
    """Return one breach description per threshold the metrics cross."""
    breaches = []
    if metrics.error_rate > thresholds.max_error_rate:
        breaches.append(
            f"error rate {metrics.error_rate:.3%} exceeds "
            f"max {thresholds.max_error_rate:.3%}"
        )
    if metrics.p95_latency_ms > thresholds.max_p95_latency_ms:
        breaches.append(
            f"p95 latency {metrics.p95_latency_ms:.0f} ms exceeds "
            f"max {thresholds.max_p95_latency_ms:.0f} ms"
        )
    if metrics.success_rate < thresholds.min_success_rate:
        breaches.append(
            f"success rate {metrics.success_rate:.3%} below "
            f"min {thresholds.min_success_rate:.3%}"
        )
    return breaches


def simulate_canary_rollout(
    service: str,
    version: str,
    previous_version: str,
    stage_metrics: list[StageMetrics],
    thresholds: HealthThresholds | None = None,
    stages: tuple[int, ...] = DEFAULT_STAGES,
) -> RolloutResult:
    """Simulate a staged canary rollout.

    ``stage_metrics`` must have one entry per stage attempted; the
    rollout stops at the first stage whose metrics breach a health
    threshold and rolls back to ``previous_version``.
    """
    thresholds = thresholds or HealthThresholds()
    result = RolloutResult(
        service=service, version=version, previous_version=previous_version,
        completed=False, rolled_back=False,
    )
    for percent, metrics in zip(stages, stage_metrics):
        breaches = check_health(metrics, thresholds)
        if breaches:
            result.stages.append(
                StageResult(
                    stage_percent=percent, metrics=metrics,
                    promoted=False, breaches=breaches,
                )
            )
            result.rolled_back = True
            result.rollback_events.append(
                f"Stage {percent}%: health gate failed "
                f"({'; '.join(breaches)}); rolled back "
                f"{version} -> {previous_version}, traffic on new "
                "version now 0%."
            )
            return result
        result.stages.append(
            StageResult(
                stage_percent=percent, metrics=metrics, promoted=True,
            )
        )
    result.completed = len(result.stages) == len(stages)
    return result
