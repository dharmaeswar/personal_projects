"""Production serving monitor: latency SLOs, output-discrepancy checks, health.

The other modules in this package answer "will this model serve fast
enough?" before it ships. This one answers the questions an AI Lab
engineer asks after it ships: is the serving deployment still inside
its latency budget, do production outputs still match the research
reference, and when they do not, where should the investigation start?

Everything is deterministic and stdlib-only. Latencies and outputs are
plain numbers supplied by the caller — this module never talks to a
real serving system and never claims a measurement of real hardware.
"""

import math
from dataclasses import dataclass, field


def _percentile(sorted_values, pct):
    """Nearest-rank percentile of an already sorted list."""
    if not sorted_values:
        raise ValueError("need at least one sample")
    rank = math.ceil(pct / 100.0 * len(sorted_values))
    return sorted_values[max(0, min(rank - 1, len(sorted_values) - 1))]


@dataclass(frozen=True)
class LatencySLO:
    """Latency budget for one serving deployment, in milliseconds."""

    p50_ms: float
    p95_ms: float
    p99_ms: float

    def __post_init__(self):
        if not (0 < self.p50_ms <= self.p95_ms <= self.p99_ms):
            raise ValueError("SLO budgets must be positive and p50 <= p95 <= p99")


@dataclass
class LatencyReport:
    """Latency percentiles for a recorded window, checked against an SLO."""

    samples: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    slo: LatencySLO
    breaches: tuple

    @property
    def passes(self):
        return not self.breaches

    @property
    def bottleneck(self):
        """Rough call on what dominates the tail: a p99 far above p95
        points at occasional stalls (GC, queueing, preemption); a p50
        near the p95 budget points at a systematically slow path."""
        if self.p99_ms > 2 * self.p95_ms:
            return "tail-stall"
        if self.p50_ms > 0.8 * self.slo.p95_ms:
            return "systematic"
        return "none"


def check_latency(latencies_ms, slo):
    """Summarise per-token latencies and check them against ``slo``.

    ``latencies_ms`` is a flat list of measured per-token latencies.
    Returns a :class:`LatencyReport`; ``breaches`` names every SLO
    percentile the window missed.
    """
    if not latencies_ms:
        raise ValueError("need at least one latency sample")
    if any(v <= 0 for v in latencies_ms):
        raise ValueError("latencies must be positive")
    ordered = sorted(latencies_ms)
    breaches = []
    p50 = _percentile(ordered, 50)
    p95 = _percentile(ordered, 95)
    p99 = _percentile(ordered, 99)
    if p50 > slo.p50_ms:
        breaches.append("p50")
    if p95 > slo.p95_ms:
        breaches.append("p95")
    if p99 > slo.p99_ms:
        breaches.append("p99")
    return LatencyReport(
        samples=len(latencies_ms),
        mean_ms=round(sum(latencies_ms) / len(latencies_ms), 3),
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        max_ms=max(latencies_ms),
        slo=slo,
        breaches=tuple(breaches),
    )


@dataclass
class OutputComparison:
    """Research-reference vs production output comparison."""

    compared: int
    max_abs_diff: float
    mean_abs_diff: float
    worst_index: int
    over_tolerance: int
    tolerance: float

    @property
    def passes(self):
        return self.over_tolerance == 0

    @property
    def fraction_over_tolerance(self):
        return self.over_tolerance / self.compared if self.compared else 0.0


def compare_outputs(reference, production, tolerance):
    """Compare two numeric output vectors element by element.

    ``reference`` is what the research model produced; ``production``
    is what the serving deployment produced for the same inputs.
    Returns an :class:`OutputComparison`. A difference is only a
    discrepancy when it exceeds ``tolerance`` — small numeric noise
    from dtype or kernel order is expected, not a bug.
    """
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    if len(reference) != len(production):
        raise ValueError("reference and production must have the same length")
    if not reference:
        raise ValueError("need at least one output value")
    diffs = [abs(a - b) for a, b in zip(reference, production)]
    worst = max(range(len(diffs)), key=lambda i: diffs[i])
    return OutputComparison(
        compared=len(diffs),
        max_abs_diff=round(max(diffs), 6),
        mean_abs_diff=round(sum(diffs) / len(diffs), 6),
        worst_index=worst,
        over_tolerance=sum(1 for d in diffs if d > tolerance),
        tolerance=tolerance,
    )


@dataclass
class DiscrepancyFinding:
    """One candidate cause for a production/research output mismatch."""

    cause: str
    likelihood: str  # "likely", "possible", "unlikely"
    evidence: str
    check: str  # what to run next to confirm or rule it out


def investigate_discrepancy(comparison, *, dtype_changed=False,
                            batching_changed=False, kernel_changed=False,
                            preprocessing_changed=False,
                            diff_grows_with_length=False):
    """Rank likely causes for a failed :func:`compare_outputs` check.

    The caller states what changed between the research run and the
    serving deployment; the function turns those facts plus the shape
    of the difference into an ordered triage list. It never claims a
    root cause — each finding names the check that would confirm it.
    Returns a list of :class:`DiscrepancyFinding`, most likely first.
    """
    if comparison.passes:
        return [DiscrepancyFinding(
            cause="no discrepancy",
            likelihood="likely",
            evidence="all outputs within tolerance",
            check="no action needed; keep the comparison in the regression suite",
        )]
    findings = []
    if preprocessing_changed:
        findings.append(DiscrepancyFinding(
            cause="data preprocessing / tokenization mismatch",
            likelihood="likely",
            evidence=(f"{comparison.over_tolerance}/{comparison.compared} outputs "
                      f"over tolerance, worst at index {comparison.worst_index}"),
            check="diff the token ids and feature vectors fed to research vs production",
        ))
    if dtype_changed and comparison.mean_abs_diff <= 10 * comparison.tolerance:
        findings.append(DiscrepancyFinding(
            cause="quantization drift (dtype change)",
            likelihood="likely",
            evidence=(f"mean abs diff {comparison.mean_abs_diff} is small "
                      f"relative to tolerance {comparison.tolerance}"),
            check="re-run the same inputs in the research dtype and compare again",
        ))
    if diff_grows_with_length:
        findings.append(DiscrepancyFinding(
            cause="numerical accumulation / kernel difference over long sequences",
            likelihood="possible",
            evidence="difference grows with sequence length",
            check="compare short vs long sequences; check kernel and reduction order",
        ))
    if batching_changed:
        findings.append(DiscrepancyFinding(
            cause="continuous-batching nondeterminism (padding / KV-cache reuse)",
            likelihood="possible",
            evidence="batching or scheduling changed between research and production",
            check="serve the same inputs one at a time and compare with the batched run",
        ))
    if kernel_changed:
        findings.append(DiscrepancyFinding(
            cause="kernel replacement (tiled / fused kernel vs reference)",
            likelihood="possible",
            evidence="kernel implementation changed between research and production",
            check="run the reference kernel and the production kernel on identical inputs",
        ))
    if not findings:
        findings.append(DiscrepancyFinding(
            cause="unexplained drift",
            likelihood="possible",
            evidence=(f"max abs diff {comparison.max_abs_diff} with no "
                      f"recorded change in dtype, batching, kernel or preprocessing"),
            check="log the full input, model version and config for a failing case and bisect",
        ))
    return findings


@dataclass
class ServingSnapshot:
    """One health snapshot of a serving deployment."""

    gpu_memory_used_gb: float
    gpu_memory_total_gb: float
    gpu_utilization: float  # 0.0 - 1.0
    throughput_tokens_per_sec: float
    error_rate: float  # 0.0 - 1.0
    latency: LatencyReport

    @property
    def memory_pressure(self):
        return self.gpu_memory_used_gb / self.gpu_memory_total_gb

    def health(self):
        """Overall verdict plus the reasons behind it.

        Thresholds are the kind of defaults an on-call engineer would
        start from, not measurements: memory pressure above 0.9 risks
        OOM evictions, utilisation below 0.2 wastes an accelerator,
        and an error rate above 1% is a page, not a warning.
        """
        reasons = []
        if self.memory_pressure > 0.9:
            reasons.append("gpu memory pressure above 90%")
        if self.gpu_utilization < 0.2:
            reasons.append("gpu utilisation below 20% (under-used accelerator)")
        if self.error_rate > 0.01:
            reasons.append(f"error rate {self.error_rate:.1%} above 1%")
        if not self.latency.passes:
            reasons.append(f"latency SLO breached: {', '.join(self.latency.breaches)}")
        if self.error_rate > 0.05 or self.memory_pressure > 0.95:
            verdict = "critical"
        elif reasons:
            verdict = "degraded"
        else:
            verdict = "healthy"
        return {"verdict": verdict, "reasons": reasons}
