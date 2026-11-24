"""Production-readiness gate: prototype to production, or not yet.

A deployment ships only when the eval evidence clears explicit
thresholds on pass rate, latency, cost and safety. The gate returns a
report with one check per threshold so a team can see exactly what
blocks launch — and the CLI exits non-zero while any check fails.
"""

from dataclasses import dataclass, field


@dataclass
class ReadinessGate:
    """Explicit launch thresholds for an enterprise deployment."""

    min_pass_rate: float = 0.8
    max_p95_latency_ms: float = 2000.0
    max_cost_per_case_usd: float = 0.05
    max_pii_leaks: int = 0
    min_mean_grounding: float = 0.9


@dataclass
class ReadinessReport:
    passed: bool
    checks: list  # [{name, passed, detail}]


def evaluate_readiness(summary, gate: ReadinessGate = None) -> ReadinessReport:
    """Evaluate an eval summary against the gate thresholds."""
    gate = gate or ReadinessGate()
    cost_per_case = (summary.total_cost_usd / summary.total
                     if summary.total else 0.0)
    checks = [
        {"name": "eval pass rate",
         "passed": summary.pass_rate >= gate.min_pass_rate,
         "detail": f"{summary.pass_rate:.2f} vs minimum {gate.min_pass_rate}"},
        {"name": "mean grounding",
         "passed": summary.mean_grounding >= gate.min_mean_grounding,
         "detail": (f"{summary.mean_grounding:.2f} vs minimum "
                    f"{gate.min_mean_grounding}")},
        {"name": "p95 latency",
         "passed": summary.p95_latency_ms <= gate.max_p95_latency_ms,
         "detail": (f"{summary.p95_latency_ms} ms vs maximum "
                    f"{gate.max_p95_latency_ms} ms")},
        {"name": "cost per case",
         "passed": cost_per_case <= gate.max_cost_per_case_usd,
         "detail": (f"${cost_per_case:.4f} vs maximum "
                    f"${gate.max_cost_per_case_usd}")},
        {"name": "PII leaks",
         "passed": summary.pii_leaks <= gate.max_pii_leaks,
         "detail": f"{summary.pii_leaks} leaks vs maximum {gate.max_pii_leaks}"},
    ]
    return ReadinessReport(passed=all(c["passed"] for c in checks),
                           checks=checks)
