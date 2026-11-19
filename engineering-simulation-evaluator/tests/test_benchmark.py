import pytest

from eng_sim_evaluator.beam import Beam
from eng_sim_evaluator.benchmark import (
    Requirements,
    compare_solver_designs,
    evaluate_design,
    rank_designs,
)
from eng_sim_evaluator.metrics import mae, max_abs_error, rmse, within_tolerance


@pytest.fixture
def req():
    return Requirements(max_tip_deflection=0.02, max_stress=200e6, max_mass=200.0)


def test_feasible_design_scores_above_one(req):
    beam = Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9)
    result = evaluate_design("slim", beam, 1000.0, req)
    assert result.feasible is True
    assert result.score > 1.0


def test_infeasible_design_flagged(req):
    # Very heavy load: deflection and stress both exceed the limits.
    beam = Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9)
    result = evaluate_design("overloaded", beam, 200_000.0, req)
    assert result.feasible is False
    assert result.score < 1.0


def test_ranking_puts_best_first(req):
    slim = Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9)
    chunky = Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9)
    results = rank_designs([
        evaluate_design("slim", slim, 1000.0, req),
        evaluate_design("chunky", chunky, 1000.0, req),
    ])
    assert results[0].name == "chunky"  # stiffer beam, larger safety margins
    assert results[0].score > results[1].score


def test_compare_solver_designs_exact_match():
    ref = [0.001, 0.002, 0.003]
    out = compare_solver_designs(ref, ref, tolerance_m=1e-6)
    assert out["mae_m"] == pytest.approx(0.0)
    assert out["within_tolerance"] == pytest.approx(1.0)
    assert out["n_designs"] == 3


def test_compare_solver_designs_off_by_known_amount():
    ref = [0.001, 0.002]
    proposed = [0.0015, 0.0025]
    out = compare_solver_designs(proposed, ref, tolerance_m=1e-3)
    assert out["mae_m"] == pytest.approx(0.0005)
    assert out["max_abs_error_m"] == pytest.approx(0.0005)
    assert out["within_tolerance"] == pytest.approx(1.0)
    out2 = compare_solver_designs(proposed, ref, tolerance_m=1e-4)
    assert out2["within_tolerance"] == pytest.approx(0.0)


def test_metrics():
    assert mae([1.0, 2.0], [1.5, 2.5]) == pytest.approx(0.5)
    assert rmse([1.0, 2.0], [1.0, 2.0]) == pytest.approx(0.0)
    assert max_abs_error([1.0, 3.0], [1.0, 2.0]) == pytest.approx(1.0)
    assert within_tolerance([1.0, 2.0], [1.0, 2.0], 0.0) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        mae([], [])
    with pytest.raises(ValueError):
        mae([1.0], [1.0, 2.0])


def test_requirements_reject_bad_limits():
    with pytest.raises(ValueError):
        Requirements(max_tip_deflection=0.0, max_stress=200e6)
