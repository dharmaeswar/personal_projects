import pytest

from eval_platform.provenance import EvalRun, RunLedger


def _run(run_id="r1", model="m1", dataset="d1", scenarios="s1", metric_v=1):
    return EvalRun(run_id, "intervention_rate", metric_v, "code1", model,
                   dataset, scenarios, "simulation")


def test_record_and_lookup():
    ledger = RunLedger()
    ledger.record(_run())
    assert ledger.get("r1").model_version == "m1"
    assert ledger.runs_for_model("m1")[0].run_id == "r1"
    assert ledger.runs_for_metric("intervention_rate")[0].run_id == "r1"


def test_conflicting_rerecord_rejected():
    ledger = RunLedger()
    ledger.record(_run())
    with pytest.raises(ValueError):
        ledger.record(_run(model="m2"))
    ledger.record(_run())  # identical re-record is fine


def test_comparability_requires_same_dataset_and_scenarios():
    a = _run("a", model="m1")
    b = _run("b", model="m2")
    assert a.comparable_with(b)
    assert not a.comparable_with(_run("c", model="m2", dataset="d2"))
    assert not a.comparable_with(_run("c", model="m2", scenarios="s2"))
    assert not a.comparable_with(_run("c", model="m2", metric_v=2))
