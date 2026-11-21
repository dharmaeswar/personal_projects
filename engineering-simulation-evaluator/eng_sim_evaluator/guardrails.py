"""CI guardrails for agent-produced changes.

An agent-proposed change to a simulator model lands only when every
guardrail passes:

1. Static analysis — the change payload is a known shape: beam parameters
   and load are positive numbers, no unknown fields, no extra keys.
2. Golden-reference comparison — the changed simulator's outputs stay
   within tolerance of the frozen golden reference for every case.
3. Provenance — the change carries a provenance record tying it to the
   tool call, inputs and golden version that produced it.

A blocked change lists every failed guardrail so the agent can fix it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .beam import Beam
from .golden import (
    GOLDEN_VERSION,
    GoldenCase,
    compare_golden,
    compute_outputs,
)
from .provenance import Provenance

_ALLOWED_CHANGE_FIELDS = {
    "length_m",
    "width_m",
    "height_m",
    "youngs_modulus_pa",
    "density_kg_m3",
    "load_n",
}


@dataclass
class GateResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "reasons": list(self.reasons)}


def static_check(change: dict) -> list[str]:
    """Validate the shape of an agent-proposed change; returns violations."""
    violations: list[str] = []
    unknown = sorted(set(change) - _ALLOWED_CHANGE_FIELDS)
    if unknown:
        violations.append(f"unknown change fields: {', '.join(unknown)}")
    for name in sorted(_ALLOWED_CHANGE_FIELDS & set(change)):
        value = change[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            violations.append(f"{name} must be a number, got {value!r}")
        elif value <= 0:
            violations.append(f"{name} must be positive, got {value}")
    return violations


def apply_change(base_beam: Beam, base_load: float, change: dict) -> tuple[Beam, float]:
    """Return the beam and load a change describes, starting from a base."""
    beam_kwargs = {
        "length": change.get("length_m", base_beam.length),
        "width": change.get("width_m", base_beam.width),
        "height": change.get("height_m", base_beam.height),
        "youngs_modulus": change.get(
            "youngs_modulus_pa", base_beam.youngs_modulus
        ),
        "density": change.get("density_kg_m3", base_beam.density),
    }
    return Beam(**beam_kwargs), change.get("load_n", base_load)


def gate_change(
    change: dict,
    golden_case: GoldenCase,
    provenance: Provenance | None,
) -> GateResult:
    """Run every guardrail on a proposed change to one golden case."""
    reasons: list[str] = []
    violations = static_check(change)
    if violations:
        reasons.extend(f"static analysis: {v}" for v in violations)
        return GateResult(allowed=False, reasons=reasons)
    if provenance is None:
        reasons.append("provenance: no provenance record attached to the change")
        return GateResult(allowed=False, reasons=reasons)
    if provenance.golden_version != GOLDEN_VERSION:
        reasons.append(
            "provenance: golden version "
            f"{provenance.golden_version!r} does not match {GOLDEN_VERSION!r}"
        )
    new_beam, new_load = apply_change(golden_case.beam, golden_case.load, change)
    try:
        candidate = compute_outputs(new_beam, new_load)
    except ValueError as exc:
        reasons.append(f"golden comparison ({golden_case.name}): {exc}")
        return GateResult(allowed=False, reasons=reasons)
    comparison = compare_golden(golden_case, candidate)
    if not comparison.passed:
        failed = [f.field for f in comparison.fields if not f.within_tolerance]
        reasons.append(
            f"golden comparison ({golden_case.name}): out of tolerance: "
            + ", ".join(failed)
        )
    return GateResult(allowed=not reasons, reasons=reasons)
