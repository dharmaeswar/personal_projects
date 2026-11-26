import pytest

from eval_platform import EvalMetricsPlatform
from eval_platform.gates import Gate
from eval_platform.provenance import EvalRun


def _platform():
    p = EvalMetricsPlatform()
    p.register_metric("intervention_rate", "desc", "rate", "rate",
                      slice_dims=("road_type",), higher_is_better=False)
    p.record_run(EvalRun("r1", "intervention_rate", 1, "code1", "m1",
                         "d1", "s1", "simulation"))
    return p


def test_end_to_end_register_run_compute_compare_gate():
    p = _platform()
    p.add_gate(Gate("intervention_rate", max_regression=0.005, higher_is_better=False))
    r = p.compute_metric("r1", "intervention_rate", "highway", [1, 0, 0] * 100, 300)
    assert r.value == pytest.approx(1 / 3)
    comp = p.compare_models("intervention_rate", 150, 1000, 90, 1000)
    assert comp.verdict == "improvement"
    summary = p.ci_check("m2", {"intervention_rate": comp})
    assert summary["release_ready"] is True


def test_compute_unknown_run_or_metric_rejected():
    p = _platform()
    with pytest.raises(ValueError):
        p.compute_metric("nope", "intervention_rate", "highway", [0], 1)
    p.record_run(EvalRun("r2", "missing_metric", 1, "code1", "m1", "d1", "s1", "simulation"))
    with pytest.raises(ValueError):
        p.compute_metric("r2", "missing_metric", "highway", [0], 1)


def test_compare_unknown_metric_rejected():
    p = EvalMetricsPlatform()
    with pytest.raises(ValueError):
        p.compare_models("nope", 1, 100, 1, 100)


def test_diagnose_delegates_to_classifier():
    p = _platform()
    assert p.diagnose(coverage=0.5, missing_inputs=3, failed_jobs=0,
                      total_jobs=10, metric_changed=True).startswith("data:")
