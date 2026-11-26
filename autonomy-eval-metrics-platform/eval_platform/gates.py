"""Regression gates and release evidence.

A gate binds a metric to a threshold (e.g. intervention rate must not rise
more than 0.5 points, or perception recall must stay above 0.92) and a
comparison verdict. The release evidence report collects the gate outcomes
for one candidate model version across its metrics and sources, so a
release team can see, in one place, what passed, what failed, and what was
inconclusive — and whether the evidence even covers the decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .compare import Comparison


@dataclass
class Gate:
    metric_name: str
    max_regression: float | None = None  # largest tolerated worsening (absolute)
    min_value: float | None = None       # floor the candidate must stay above
    higher_is_better: bool = True

    def evaluate(self, comparison: Comparison) -> tuple[bool, str]:
        if comparison.verdict == "not_comparable":
            return False, f"{self.metric_name}: BLOCKED — {comparison.reason}"
        if comparison.verdict == "inconclusive":
            return False, f"{self.metric_name}: BLOCKED — inconclusive: {comparison.reason}"
        if comparison.candidate_value is None or comparison.delta is None:
            return False, f"{self.metric_name}: BLOCKED — no candidate value"
        worsening = -comparison.delta if self.higher_is_better else comparison.delta
        if self.max_regression is not None and worsening > self.max_regression:
            return False, (f"{self.metric_name}: FAIL — worsened by {worsening:.4f}, "
                           f"tolerance is {self.max_regression}")
        if self.min_value is not None and comparison.candidate_value < self.min_value:
            return False, (f"{self.metric_name}: FAIL — candidate {comparison.candidate_value:.4f} "
                           f"below floor {self.min_value}")
        return True, f"{self.metric_name}: PASS — {comparison.verdict} ({comparison.reason})"


@dataclass
class ReleaseEvidence:
    model_version: str
    gate_results: list[tuple[Gate, bool, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.gate_results) and all(ok for _, ok, _ in self.gate_results)

    def summary(self) -> dict:
        return {
            "model_version": self.model_version,
            "gates_total": len(self.gate_results),
            "gates_passed": sum(1 for _, ok, _ in self.gate_results if ok),
            "release_ready": self.passed,
            "details": [msg for _, _, msg in self.gate_results],
        }


def build_release_evidence(model_version: str, gates: list[Gate],
                           comparisons: dict[str, Comparison]) -> ReleaseEvidence:
    evidence = ReleaseEvidence(model_version)
    for gate in gates:
        comparison = comparisons.get(gate.metric_name)
        if comparison is None:
            evidence.gate_results.append(
                (gate, False, f"{gate.metric_name}: BLOCKED — no comparison available"))
            continue
        ok, msg = gate.evaluate(comparison)
        evidence.gate_results.append((gate, ok, msg))
    return evidence
