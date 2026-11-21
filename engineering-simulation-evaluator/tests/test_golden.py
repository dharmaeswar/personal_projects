"""Tests for golden.py: frozen reference outputs and comparisons."""

import pytest

from eng_sim_evaluator.beam import Beam
from eng_sim_evaluator.golden import compare_golden, compute_outputs, generate_golden

STEEL = Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9)


def test_compute_outputs_matches_analytic_values():
    outputs = compute_outputs(STEEL, 1000.0)
    assert outputs["tip_deflection_m"] == pytest.approx(0.0016)
    assert outputs["max_stress_pa"] == pytest.approx(12_000_000.0)
    assert outputs["first_natural_frequency_hz"] > 0


def test_compute_outputs_rejects_non_positive_load():
    with pytest.raises(ValueError):
        compute_outputs(STEEL, 0.0)


def test_generate_golden_rejects_duplicate_names():
    with pytest.raises(ValueError):
        generate_golden([("a", STEEL, 1000.0), ("a", STEEL, 500.0)])


def test_compare_golden_passes_for_exact_outputs():
    golden = generate_golden([("steel", STEEL, 1000.0)])["steel"]
    comparison = compare_golden(golden, compute_outputs(STEEL, 1000.0))
    assert comparison.passed
    assert all(f.within_tolerance for f in comparison.fields)


def test_compare_golden_fails_when_a_field_moves():
    golden = generate_golden([("steel", STEEL, 1000.0)])["steel"]
    moved = compute_outputs(STEEL, 1000.0)
    moved["tip_deflection_m"] *= 1.5
    comparison = compare_golden(golden, moved)
    assert not comparison.passed
    failed = [f.field for f in comparison.fields if not f.within_tolerance]
    assert failed == ["tip_deflection_m"]


def test_compare_golden_fails_on_missing_field():
    golden = generate_golden([("steel", STEEL, 1000.0)])["steel"]
    outputs = compute_outputs(STEEL, 1000.0)
    del outputs["max_stress_pa"]
    assert not compare_golden(golden, outputs).passed


def test_compare_golden_rejects_unknown_fields():
    golden = generate_golden([("steel", STEEL, 1000.0)])["steel"]
    outputs = compute_outputs(STEEL, 1000.0)
    outputs["surprise"] = 1.0
    with pytest.raises(ValueError):
        compare_golden(golden, outputs)
