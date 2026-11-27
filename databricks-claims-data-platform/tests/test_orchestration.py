"""Tests for the ADF-style orchestration: ordering, retries, failure handling."""
import pytest

from claims_platform.orchestration import load_pipeline, run_pipeline, topo_order


def test_pipeline_definition_loads():
    pipeline = load_pipeline()
    assert pipeline["name"] == "claims_daily"
    assert len(pipeline["activities"]) == 5
    assert [a["name"] for a in pipeline["activities"]] == [
        "IngestRawClaims", "ValidateSilver", "PublishGold", "ScoreClaimsML",
        "RefreshApiCache"]


def test_topo_order_respects_dependencies():
    pipeline = load_pipeline()
    order = topo_order(pipeline["activities"])
    assert order.index("IngestRawClaims") < order.index("ValidateSilver")
    assert order.index("ValidateSilver") < order.index("PublishGold")
    assert order.index("PublishGold") < order.index("ScoreClaimsML")
    assert order.index("ScoreClaimsML") < order.index("RefreshApiCache")


def test_topo_order_rejects_cycles():
    acts = [{"name": "a", "dependsOn": ["b"]}, {"name": "b", "dependsOn": ["a"]}]
    with pytest.raises(ValueError, match="cycle"):
        topo_order(acts)


def test_run_succeeds_and_logs_attempts():
    pipeline = load_pipeline()
    seen = []
    log = run_pipeline(pipeline, lambda name: seen.append(name))
    assert log["status"] == "Succeeded"
    assert seen == ["IngestRawClaims", "ValidateSilver", "PublishGold",
                    "ScoreClaimsML", "RefreshApiCache"]
    assert all(v["status"] == "Succeeded" and v["attempts"] == 1
               for v in log["activities"].values())


def test_retry_then_success():
    pipeline = {"name": "t", "activities": [
        {"name": "flaky", "dependsOn": [], "retry": 1}]}
    calls = {"n": 0}

    def flaky(name):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure")

    log = run_pipeline(pipeline, flaky)
    assert log["status"] == "Succeeded"
    assert log["activities"]["flaky"]["attempts"] == 2


def test_failure_after_retries_marks_pipeline_failed():
    pipeline = {"name": "t", "activities": [
        {"name": "bad", "dependsOn": [], "retry": 1},
        {"name": "downstream", "dependsOn": ["bad"], "retry": 0}]}
    log = run_pipeline(pipeline, lambda name: (_ for _ in ()).throw(RuntimeError("boom")))
    assert log["status"] == "Failed"
    assert log["activities"]["bad"]["status"] == "Failed"
    assert "downstream" not in log["activities"]  # never reached
