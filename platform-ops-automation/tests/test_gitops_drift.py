"""Tests for the GitOps drift detection and rollout gate demo module."""

import pytest

from ops.gitops_drift import (
    desired_state,
    detect_drift,
    diff_container,
    diff_resource,
    format_traceparent,
    generate_synthetic_state,
    parse_traceparent,
    rollout_gate,
    summarize_drift,
)

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


def _deployment(name="platform-ops", image="platform-ops:v1.4.0", replicas=3,
                env=None, resources=None):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": "default"},
        "spec": {
            "replicas": replicas,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "web",
                            "image": image,
                            "env": env if env is not None else [{"name": "PORT", "value": "8080"}],
                            "resources": resources
                            if resources is not None
                            else {"limits": {"cpu": "500m", "memory": "512Mi"}},
                        }
                    ]
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def test_identical_state_is_in_sync():
    desired = desired_state([_deployment()])
    live = desired_state([_deployment()])
    report = detect_drift(desired, live)
    assert report["in_sync"] is True
    assert report["drifted"] == {}
    assert report["missing"] == []
    assert report["extra"] == []
    assert summarize_drift(report) == "in sync: live state matches desired state"


def test_image_drift_detected():
    desired = desired_state([_deployment()])
    live = desired_state([_deployment(image="platform-ops:v1.4.1")])
    report = detect_drift(desired, live)
    assert report["in_sync"] is False
    key = ("Deployment", "default", "platform-ops")
    entries = report["drifted"][key]
    assert any(
        e["field"] == "image"
        and e["desired"] == "platform-ops:v1.4.0"
        and e["live"] == "platform-ops:v1.4.1"
        for e in entries
    )


def test_replica_drift_detected():
    desired = desired_state([_deployment(replicas=3)])
    live = desired_state([_deployment(replicas=2)])
    report = detect_drift(desired, live)
    key = ("Deployment", "default", "platform-ops")
    assert any(
        e["field"] == "replicas" and e["desired"] == 3 and e["live"] == 2
        for e in report["drifted"][key]
    )


def test_env_drift_detected():
    desired = desired_state([_deployment()])
    live = desired_state(
        [_deployment(env=[{"name": "PORT", "value": "9090"}])]
    )
    report = detect_drift(desired, live)
    key = ("Deployment", "default", "platform-ops")
    assert any(e["field"] == "env" for e in report["drifted"][key])


def test_missing_and_extra_resources():
    desired = desired_state([_deployment("a"), _deployment("b")])
    live = desired_state([_deployment("a"), _deployment("c")])
    report = detect_drift(desired, live)
    assert ("Deployment", "default", "b") in report["missing"]
    assert ("Deployment", "default", "c") in report["extra"]
    assert report["in_sync"] is False


def test_diff_container_reports_each_field_once():
    desired_container = {
        "image": "app:v1",
        "env": [{"name": "A", "value": "1"}],
        "resources": {"limits": {"cpu": "1"}},
    }
    live_container = {
        "image": "app:v2",
        "env": [{"name": "A", "value": "2"}],
        "resources": {"limits": {"cpu": "2"}},
    }
    fields = [e["field"] for e in diff_container(desired_container, live_container)]
    assert fields == ["image", "env", "resources"]


def test_diff_container_empty_when_matching():
    container = {
        "image": "app:v1",
        "env": [{"name": "A", "value": "1"}],
        "resources": {"limits": {"cpu": "1"}},
    }
    assert diff_container(container, dict(container)) == []


def test_missing_container_reported():
    desired = _deployment()
    live = _deployment()
    live["spec"]["template"]["spec"]["containers"] = []
    entries = diff_resource(desired, live)
    assert any(e["field"] == "container" and e["desired"] == "web" for e in entries)


def test_desired_state_skips_manifests_without_identity():
    state = desired_state([{"kind": "Service"}, {"kind": None, "metadata": {"name": "x"}}])
    assert state == {}


def test_synthetic_state_has_exactly_one_drift():
    desired, live = generate_synthetic_state()
    report = detect_drift(desired, live)
    assert len(report["drifted"]) == 1
    key = ("Deployment", "default", "platform-ops")
    assert [e["field"] for e in report["drifted"][key]] == ["image"]


# ---------------------------------------------------------------------------
# Rollout gate
# ---------------------------------------------------------------------------

def test_gate_allows_clean_state_with_budget_left():
    report = detect_drift(
        desired_state([_deployment()]), desired_state([_deployment()])
    )
    gate = rollout_gate(report, error_budget_burn=0.4)
    assert gate == {"allowed": True, "reasons": []}


def test_gate_blocks_on_drift():
    report = detect_drift(
        desired_state([_deployment()]),
        desired_state([_deployment(image="platform-ops:v1.4.1")]),
    )
    gate = rollout_gate(report)
    assert gate["allowed"] is False
    assert any("drift" in r for r in gate["reasons"])


def test_gate_blocks_on_error_budget_burn():
    report = detect_drift(
        desired_state([_deployment()]), desired_state([_deployment()])
    )
    gate = rollout_gate(report, error_budget_burn=1.5)
    assert gate["allowed"] is False
    assert any("error-budget burn" in r for r in gate["reasons"])


def test_gate_allows_burn_at_exact_limit():
    report = detect_drift(
        desired_state([_deployment()]), desired_state([_deployment()])
    )
    gate = rollout_gate(report, error_budget_burn=1.0)
    assert gate["allowed"] is True


# ---------------------------------------------------------------------------
# W3C traceparent helpers
# ---------------------------------------------------------------------------

def test_traceparent_round_trip():
    header = format_traceparent(TRACE_ID, SPAN_ID, sampled=True)
    assert header == f"00-{TRACE_ID}-{SPAN_ID}-01"
    parsed = parse_traceparent(header)
    assert parsed == {"trace_id": TRACE_ID, "parent_id": SPAN_ID, "sampled": True}


def test_traceparent_unsampled_flag():
    header = format_traceparent(TRACE_ID, SPAN_ID, sampled=False)
    assert header.endswith("-00")
    assert parse_traceparent(header)["sampled"] is False


def test_traceparent_rejects_malformed():
    assert parse_traceparent("not-a-traceparent") is None
    assert parse_traceparent(f"00-{TRACE_ID}-{SPAN_ID}-02") is None
    assert parse_traceparent(None) is None
    assert parse_traceparent(f"00-{'0' * 32}-{SPAN_ID}-01") is None
    assert parse_traceparent(f"00-{TRACE_ID}-{'0' * 16}-01") is None


def test_format_traceparent_rejects_bad_ids():
    with pytest.raises(ValueError):
        format_traceparent("too-short", SPAN_ID)
    with pytest.raises(ValueError):
        format_traceparent(TRACE_ID, "UPPERCASEHEX00")
    with pytest.raises(ValueError):
        format_traceparent("0" * 32, SPAN_ID)
