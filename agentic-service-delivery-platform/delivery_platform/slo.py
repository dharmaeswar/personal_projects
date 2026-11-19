"""SLI/SLO tracking: availability, latency, error budgets, burn rate.

Observations are (service, ok, latency_ms) samples. From them the
tracker computes availability over a window, the remaining error budget
against a target, the error-budget burn rate, and latency p95, and raises
plain-language alerts when a service is breaching its SLO.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Observation:
    service: str
    ok: bool
    latency_ms: float


@dataclass
class SLOTracker:
    observations: list[Observation] = field(default_factory=list)

    def record(self, service: str, ok: bool, latency_ms: float) -> None:
        if latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        self.observations.append(Observation(service, ok, latency_ms))

    def _samples(self, service: str) -> list[Observation]:
        return [o for o in self.observations if o.service == service]

    def availability(self, service: str) -> float | None:
        samples = self._samples(service)
        if not samples:
            return None
        return sum(1 for o in samples if o.ok) / len(samples)

    def error_budget_remaining(self, service: str,
                               target: float = 0.999) -> float | None:
        """Fraction of the allowed error budget still unused (0..1+)."""
        samples = self._samples(service)
        if not samples:
            return None
        allowed_errors = (1.0 - target) * len(samples)
        actual_errors = sum(1 for o in samples if not o.ok)
        if allowed_errors <= 0:
            return 1.0 if actual_errors == 0 else 0.0
        return max(0.0, (allowed_errors - actual_errors) / allowed_errors)

    def burn_rate(self, service: str, target: float = 0.999) -> float | None:
        """Observed error rate divided by the allowed error rate.

        1.0 means errors are arriving exactly as fast as the budget
        allows; above 1.0 the budget is burning faster than planned.
        """
        samples = self._samples(service)
        if not samples:
            return None
        allowed = 1.0 - target
        if allowed <= 0:
            return float("inf") if any(not o.ok for o in samples) else 0.0
        observed = sum(1 for o in samples if not o.ok) / len(samples)
        return observed / allowed

    def latency_p95(self, service: str) -> float | None:
        samples = sorted(o.latency_ms for o in self._samples(service))
        if not samples:
            return None
        index = max(0, int(len(samples) * 0.95) - 1)
        return samples[index]

    def alerts(self, service: str, target: float = 0.999,
               burn_threshold: float = 2.0) -> list[str]:
        out: list[str] = []
        avail = self.availability(service)
        if avail is not None and avail < target:
            out.append(
                f"availability {avail:.4f} below SLO target {target:.3f}")
        burn = self.burn_rate(service, target)
        if burn is not None and burn > burn_threshold:
            out.append(
                f"error-budget burn rate {burn:.1f}x above threshold "
                f"{burn_threshold:.1f}x")
        return out

    def summary(self, service: str, target: float = 0.999) -> dict:
        return {
            "service": service,
            "samples": len(self._samples(service)),
            "availability": self.availability(service),
            "error_budget_remaining": self.error_budget_remaining(service, target),
            "burn_rate": self.burn_rate(service, target),
            "latency_p95_ms": self.latency_p95(service),
            "alerts": self.alerts(service, target),
        }
