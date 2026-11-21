"""Golden-reference store for simulator outputs.

A golden reference is the trusted output of the analytic simulator for a
fixed case (beam geometry + load), frozen at a version. Agent-produced
changes are checked against the golden values: a change that moves a
simulator output away from the golden reference is a regression, not an
improvement. All values are computed by the analytic beam model, so the
golden set is reproducible from the case definition alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .beam import Beam, first_natural_frequency, max_stress, tip_deflection

GOLDEN_VERSION = "golden-v1"

# Tolerance per output field (absolute). Tip deflection is in metres, stress
# in Pa, frequency in Hz — the tolerances are the CI thresholds an agent
# change must stay inside.
FIELD_TOLERANCES = {
    "tip_deflection_m": 1e-9,
    "max_stress_pa": 1.0,
    "first_natural_frequency_hz": 1e-6,
}


@dataclass(frozen=True)
class GoldenCase:
    """One frozen simulator case: beam, load, and the trusted outputs."""

    name: str
    beam: Beam
    load: float
    outputs: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "version": GOLDEN_VERSION,
            "beam": {
                "length_m": self.beam.length,
                "width_m": self.beam.width,
                "height_m": self.beam.height,
                "youngs_modulus_pa": self.beam.youngs_modulus,
                "density_kg_m3": self.beam.density,
            },
            "load_n": self.load,
            "outputs": dict(self.outputs),
        }


def compute_outputs(beam: Beam, load: float) -> dict[str, float]:
    """Run the analytic simulator and return the reference outputs."""
    if load <= 0:
        raise ValueError(f"load must be positive, got {load}")
    return {
        "tip_deflection_m": tip_deflection(beam, load),
        "max_stress_pa": max_stress(beam, load),
        "first_natural_frequency_hz": first_natural_frequency(beam),
    }


def generate_golden(cases: list[tuple[str, Beam, float]]) -> dict[str, GoldenCase]:
    """Build the golden set from case definitions (name, beam, load)."""
    golden: dict[str, GoldenCase] = {}
    for name, beam, load in cases:
        if name in golden:
            raise ValueError(f"duplicate golden case name: {name}")
        golden[name] = GoldenCase(
            name=name, beam=beam, load=load, outputs=compute_outputs(beam, load)
        )
    return golden


@dataclass
class FieldComparison:
    field: str
    golden: float
    candidate: float
    abs_diff: float
    tolerance: float
    within_tolerance: bool

    def as_dict(self) -> dict:
        return {
            "field": self.field,
            "golden": self.golden,
            "candidate": self.candidate,
            "abs_diff": self.abs_diff,
            "tolerance": self.tolerance,
            "within_tolerance": self.within_tolerance,
        }


@dataclass
class GoldenComparison:
    case_name: str
    version: str
    fields: list[FieldComparison]
    passed: bool

    def as_dict(self) -> dict:
        return {
            "case": self.case_name,
            "version": self.version,
            "passed": self.passed,
            "fields": [f.as_dict() for f in self.fields],
        }


def compare_golden(
    golden_case: GoldenCase, candidate_outputs: dict[str, float]
) -> GoldenComparison:
    """Compare candidate outputs against one golden case, field by field.

    Unknown candidate fields are rejected; missing fields fail the case.
    """
    unknown = sorted(set(candidate_outputs) - set(FIELD_TOLERANCES))
    if unknown:
        raise ValueError(f"unknown output fields: {', '.join(unknown)}")
    fields: list[FieldComparison] = []
    for name, tolerance in FIELD_TOLERANCES.items():
        golden_value = golden_case.outputs[name]
        if name not in candidate_outputs:
            fields.append(
                FieldComparison(
                    field=name,
                    golden=golden_value,
                    candidate=float("nan"),
                    abs_diff=float("inf"),
                    tolerance=tolerance,
                    within_tolerance=False,
                )
            )
            continue
        candidate = candidate_outputs[name]
        diff = abs(candidate - golden_value)
        fields.append(
            FieldComparison(
                field=name,
                golden=golden_value,
                candidate=candidate,
                abs_diff=diff,
                tolerance=tolerance,
                within_tolerance=diff <= tolerance,
            )
        )
    return GoldenComparison(
        case_name=golden_case.name,
        version=GOLDEN_VERSION,
        fields=fields,
        passed=all(f.within_tolerance for f in fields),
    )
