"""Benchmark: score candidate engineering designs against requirements.

A design is a Beam plus a tip load. Requirements cap tip deflection and max
stress and (optionally) mass. Each design is scored on feasibility plus
normalised safety margins, so designs can be ranked and an AI-proposed design
set can be compared with a reference solver's designs on the same task.
"""

from __future__ import annotations

from dataclasses import dataclass

from .beam import Beam, max_stress, tip_deflection
from .metrics import mae, max_abs_error, within_tolerance


@dataclass(frozen=True)
class Requirements:
    max_tip_deflection: float  # m
    max_stress: float          # Pa
    max_mass: float | None = None  # kg, optional

    def __post_init__(self) -> None:
        if self.max_tip_deflection <= 0 or self.max_stress <= 0:
            raise ValueError("limits must be positive")
        if self.max_mass is not None and self.max_mass <= 0:
            raise ValueError("max_mass must be positive")


@dataclass
class DesignResult:
    name: str
    tip_deflection: float
    stress: float
    mass: float
    feasible: bool
    score: float  # higher is better; feasible designs score above 1.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "tip_deflection_m": round(self.tip_deflection, 6),
            "stress_MPa": round(self.stress / 1e6, 3),
            "mass_kg": round(self.mass, 3),
            "feasible": self.feasible,
            "score": round(self.score, 4),
        }


def evaluate_design(name: str, beam: Beam, load: float, req: Requirements) -> DesignResult:
    tip = tip_deflection(beam, load)
    stress = max_stress(beam, load)
    mass = beam.mass
    feasible = tip <= req.max_tip_deflection and stress <= req.max_stress
    if req.max_mass is not None:
        feasible = feasible and mass <= req.max_mass
    # Margins: how far inside each limit the design sits (1.0 = exactly at limit).
    # Mass only gates feasibility; the score ranks on deflection/stress margin.
    deflection_margin = req.max_tip_deflection / tip if tip > 0 else float("inf")
    stress_margin = req.max_stress / stress if stress > 0 else float("inf")
    margin = min(deflection_margin, stress_margin)
    # Feasible designs score above 1, growing with safety margin (capped);
    # infeasible designs score below 1.
    score = (1.0 + 0.1 * min(margin - 1.0, 10.0)) if feasible else min(margin, 1.0) * 0.9
    return DesignResult(name, tip, stress, mass, feasible, score)


def rank_designs(results: list[DesignResult]) -> list[DesignResult]:
    return sorted(results, key=lambda r: r.score, reverse=True)


def compare_solver_designs(
    proposed_tip_deflections: list[float],
    reference_tip_deflections: list[float],
    tolerance_m: float,
) -> dict:
    """Score an AI-proposed design set against a reference solver's outputs.

    Returns MAE, max error and the share of proposals within tolerance of the
    reference deflection — the same style of check used to grade model
    outputs on an engineering benchmark task.
    """
    if not proposed_tip_deflections or not reference_tip_deflections:
        raise ValueError("design lists must be non-empty")
    if len(proposed_tip_deflections) != len(reference_tip_deflections):
        raise ValueError("proposed and reference lists must have the same length")
    return {
        "n_designs": len(proposed_tip_deflections),
        "mae_m": mae(proposed_tip_deflections, reference_tip_deflections),
        "max_abs_error_m": max_abs_error(proposed_tip_deflections, reference_tip_deflections),
        "within_tolerance": within_tolerance(
            proposed_tip_deflections, reference_tip_deflections, tolerance_m
        ),
    }
