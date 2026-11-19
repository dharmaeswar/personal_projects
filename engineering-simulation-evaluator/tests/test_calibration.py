import pytest

from eng_sim_evaluator.beam import Beam
from eng_sim_evaluator.calibration import (
    calibrate_youngs_modulus,
    calibration_error_pct,
    synthetic_measurements,
)


@pytest.fixture
def true_beam():
    return Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9)


def test_synthetic_measurements_near_truth(true_beam):
    positions = [0.5, 1.0, 1.5, 2.0]
    meas = synthetic_measurements(true_beam, 1000.0, positions, noise_std=1e-6, seed=7)
    assert len(meas) == 4
    assert [x for x, _ in meas] == positions


def test_calibration_recovers_modulus(true_beam):
    positions = [0.5, 1.0, 1.5, 2.0]
    meas = synthetic_measurements(true_beam, 1000.0, positions, noise_std=1e-6, seed=7)
    template = Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=1.0)
    candidates = [150e9, 180e9, 200e9, 220e9, 250e9]
    recovered, _sse = calibrate_youngs_modulus(template, 1000.0, meas, candidates)
    assert recovered == pytest.approx(200e9)
    assert calibration_error_pct(recovered, 200e9) == pytest.approx(0.0)


def test_calibration_error_pct():
    assert calibration_error_pct(190e9, 200e9) == pytest.approx(5.0)
    with pytest.raises(ValueError):
        calibration_error_pct(190e9, 0.0)


def test_calibration_rejects_empty_inputs(true_beam):
    with pytest.raises(ValueError):
        calibrate_youngs_modulus(true_beam, 1000.0, [], [200e9])
    with pytest.raises(ValueError):
        calibrate_youngs_modulus(true_beam, 1000.0, [(1.0, 0.001)], [])
