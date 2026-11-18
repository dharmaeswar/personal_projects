"""Release report generator.

Renders one human-readable text report per release: gate results
(pass/fail per gate with reasons), the rollout timeline, and any
rollback events. Pure formatting — it takes the gate report and the
rollout result and returns text.
"""

from __future__ import annotations

from .gates import GateReport
from .rollout import RolloutResult


def render_report(gate_report: GateReport, rollout: RolloutResult | None) -> str:
    lines = [
        f"Release report: {gate_report.service} {gate_report.version}",
        "=" * 60,
        "",
        "Readiness gates "
        f"({gate_report.passed_count}/{len(gate_report.results)} passed):",
    ]
    for result in gate_report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"  [{status}] {result.name}")
        if result.detail:
            lines.append(f"         {result.detail}")
        if not result.passed:
            lines.append(f"         BLOCKED: {result.reason}")
    lines.append("")
    lines.append(
        "Overall: "
        + ("READY TO SHIP" if gate_report.passed else "BLOCKED — do not ship")
    )
    lines.append("")
    if rollout is None:
        lines.append("Rollout: not attempted (release blocked by gates).")
    else:
        lines.append("Rollout timeline:")
        for stage in rollout.stages:
            outcome = "promoted" if stage.promoted else "FAILED health gate"
            m = stage.metrics
            lines.append(
                f"  {stage.stage_percent:>3}% traffic — {outcome} "
                f"(error {m.error_rate:.3%}, p95 {m.p95_latency_ms:.0f} ms, "
                f"success {m.success_rate:.3%})"
            )
            for breach in stage.breaches:
                lines.append(f"         breach: {breach}")
        if rollout.completed:
            lines.append(
                f"Rollout complete: 100% of traffic on {rollout.version}."
            )
        if rollout.rolled_back:
            lines.append("Rollback events:")
            for event in rollout.rollback_events:
                lines.append(f"  - {event}")
            lines.append(
                f"Final state: 0% of traffic on {rollout.version}; "
                f"{rollout.previous_version} restored."
            )
    return "\n".join(lines) + "\n"
