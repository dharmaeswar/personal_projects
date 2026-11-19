import math

import pytest

from eng_sim_evaluator.beam import (
    Beam,
    deflection,
    deflection_profile,
    first_natural_frequency,
    max_stress,
    tip_deflection,
)


@pytest.fixture
def beam():
    # Steel cantilever: 2 m long, 0.1 m wide, 0.05 m tall, E = 200 GPa.
    return Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9)


def test_moment_of_inertia(beam):
    assert beam.moment_of_inertia == pytest.approx(0.1 * 0.05 ** 3 / 12)


def test_tip_deflection_matches_formula(beam):
    load = 1000.0
    expected = load * 2.0 ** 3 / (3 * 200e9 * beam.moment_of_inertia)
    assert tip_deflection(beam, load) == pytest.approx(expected, rel=1e-12)


def test_deflection_zero_at_wall(beam):
    assert deflection(beam, 1000.0, 0.0) == pytest.approx(0.0, abs=1e-15)


def test_deflection_grows_toward_tip(beam):
    profile = deflection_profile(beam, 1000.0, n_points=6)
    values = [d for _, d in profile]
    assert values == sorted(values)
    assert values[-1] == pytest.approx(tip_deflection(beam, 1000.0))


def test_deflection_profile_endpoints(beam):
    profile = deflection_profile(beam, 500.0, n_points=5)
    assert profile[0][0] == pytest.approx(0.0)
    assert profile[-1][0] == pytest.approx(2.0)
    assert len(profile) == 5


def test_max_stress_formula(beam):
    load = 1000.0
    expected = load * 2.0 * (0.05 / 2) / beam.moment_of_inertia
    assert max_stress(beam, load) == pytest.approx(expected, rel=1e-12)
    assert max_stress(beam, load) < 250e6  # well under steel yield


def test_zero_load_gives_zero_response(beam):
    assert tip_deflection(beam, 0.0) == 0.0
    assert max_stress(beam, 0.0) == 0.0


def test_natural_frequency_positive_and_sane(beam):
    f1 = first_natural_frequency(beam)
    assert 1.0 < f1 < 500.0


def test_invalid_dimensions_rejected():
    with pytest.raises(ValueError):
        Beam(length=-1.0, width=0.1, height=0.05, youngs_modulus=200e9)
    with pytest.raises(ValueError):
        Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=0.0)


def test_position_outside_beam_rejected(beam):
    with pytest.raises(ValueError):
        deflection(beam, 1000.0, 2.5)
    with pytest.raises(ValueError):
        deflection(beam, 1000.0, -0.1)


def test_stiffer_beam_deflects_less(beam):
    stiff = Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9)
    assert tip_deflection(stiff, 1000.0) < tip_deflection(beam, 1000.0)
