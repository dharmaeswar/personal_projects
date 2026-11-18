"""Tests for the Platform Ops Automation demo project."""

import json
import os
import threading
import urllib.request

import pytest
import yaml

from ops.log_analysis import (
    flag_spike_minutes,
    p50,
    p95,
    parse_log,
    percentile,
    per_minute_error_rate,
)
from service.app import LATENCY_BUCKETS, Metrics, build_server

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_lines(minute, statuses):
    """Build synthetic log lines for one minute (10:MM) with given statuses."""
    lines = []
    for i, status in enumerate(statuses):
        lines.append(f"2026-11-18T10:{minute:02d}:{i:02d}Z GET / {status} 0.050")
    return lines


# ---------------------------------------------------------------------------
# Web service (live, on an ephemeral port)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def running_service():
    server = build_server(0, host="127.0.0.1")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def _get(base_url, path):
    with urllib.request.urlopen(base_url + path, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")


def test_health_returns_ok(running_service):
    status, body = _get(running_service, "/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


def test_root_returns_demo_page(running_service):
    status, body = _get(running_service, "/")
    assert status == 200
    assert "Platform Ops Automation" in body


def test_metrics_contains_expected_metric_names(running_service):
    _get(running_service, "/")  # generate at least one request
    status, body = _get(running_service, "/metrics")
    assert status == 200
    for name in (
        "platform_ops_requests_total",
        "platform_ops_errors_total",
        "platform_ops_request_duration_seconds_bucket",
        "platform_ops_request_duration_seconds_sum",
        "platform_ops_request_duration_seconds_count",
    ):
        assert name in body
    # Histogram buckets cover the configured bounds.
    for bucket in LATENCY_BUCKETS:
        assert f'le="{bucket}"' in body
    assert 'le="+Inf"' in body


def test_metrics_request_count_increases(running_service):
    _, before = _get(running_service, "/metrics")
    count_before = int(
        [l for l in before.splitlines() if l.startswith("platform_ops_requests_total ")][0].split()[-1]
    )
    _get(running_service, "/")
    _, after = _get(running_service, "/metrics")
    count_after = int(
        [l for l in after.splitlines() if l.startswith("platform_ops_requests_total ")][0].split()[-1]
    )
    assert count_after > count_before


def test_unknown_path_returns_404(running_service):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(running_service, "/nope")
    assert excinfo.value.code == 404


# ---------------------------------------------------------------------------
# Latency statistics
# ---------------------------------------------------------------------------

def test_p50_p95_on_known_samples():
    samples = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
    assert p50(samples) == pytest.approx(0.05)
    assert p95(samples) == pytest.approx(0.10)


def test_percentile_single_sample_and_empty():
    assert percentile([0.42], 50) == pytest.approx(0.42)
    assert percentile([0.42], 95) == pytest.approx(0.42)
    assert percentile([], 50) is None
    assert p50([]) is None
    assert p95([]) is None


def test_metrics_render_counts_errors_and_buckets():
    metrics = Metrics()
    metrics.record(0.02, 200)
    metrics.record(0.3, 500)
    metrics.record(1.5, 200)
    out = metrics.render_prometheus()
    assert "platform_ops_requests_total 3" in out
    assert "platform_ops_errors_total 1" in out
    assert 'platform_ops_request_duration_seconds_bucket{le="0.05"} 1' in out
    assert 'platform_ops_request_duration_seconds_bucket{le="+Inf"} 3' in out


# ---------------------------------------------------------------------------
# Log analysis
# ---------------------------------------------------------------------------

def test_log_parser_flags_spike_minute():
    lines = _log_lines(0, [200] * 20) + _log_lines(1, [200] * 16 + [500] * 4)
    entries = parse_log("\n".join(lines))
    assert len(entries) == 40
    flagged = flag_spike_minutes(entries, threshold=0.05)
    assert len(flagged) == 1
    assert flagged[0].minute == 1


def test_log_parser_passes_clean_minute():
    lines = _log_lines(0, [200] * 20) + _log_lines(1, [200] * 20)
    entries = parse_log("\n".join(lines))
    assert flag_spike_minutes(entries, threshold=0.05) == []
    rates = per_minute_error_rate(entries)
    assert all(rate == 0.0 for (_, _, rate) in rates.values())


def test_threshold_edge_cases():
    # Exactly at the threshold: rate == threshold must NOT be flagged
    # (flagging is strictly above the threshold).
    lines = _log_lines(0, [200] * 19 + [500])  # 1/20 = 5%
    entries = parse_log("\n".join(lines))
    assert flag_spike_minutes(entries, threshold=0.05) == []
    assert flag_spike_minutes(entries, threshold=0.049) != []
    # Zero threshold flags any minute with an error, but not clean minutes.
    assert flag_spike_minutes(entries, threshold=0.0) != []
    clean = parse_log("\n".join(_log_lines(0, [200] * 10)))
    assert flag_spike_minutes(clean, threshold=0.0) == []
    # Malformed lines are skipped, not fatal.
    assert parse_log("not a log line\n" + "\n".join(_log_lines(0, [200] * 5))) != []


# ---------------------------------------------------------------------------
# Kubernetes manifests
# ---------------------------------------------------------------------------

EXPECTED_KINDS = {
    "deployment.yaml": "Deployment",
    "service.yaml": "Service",
    "hpa.yaml": "HorizontalPodAutoscaler",
    "configmap.yaml": "ConfigMap",
    "ingress.yaml": "Ingress",
}


@pytest.mark.parametrize("filename,kind", list(EXPECTED_KINDS.items()))
def test_k8s_manifest_parses_with_expected_kind(filename, kind):
    path = os.path.join(PROJECT_ROOT, "k8s", filename)
    with open(path) as f:
        doc = yaml.safe_load(f)
    assert doc["kind"] == kind
    assert doc["apiVersion"]
    assert doc["metadata"]["name"]


def test_deployment_has_probes_and_resources():
    with open(os.path.join(PROJECT_ROOT, "k8s", "deployment.yaml")) as f:
        doc = yaml.safe_load(f)
    assert doc["spec"]["replicas"] == 3
    container = doc["spec"]["template"]["spec"]["containers"][0]
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["resources"]["requests"]["cpu"] == "100m"
    assert container["resources"]["limits"]["memory"] == "256Mi"


# ---------------------------------------------------------------------------
# CI configuration
# ---------------------------------------------------------------------------

def test_ci_workflow_parses_and_has_test_and_build_jobs():
    path = os.path.join(
        PROJECT_ROOT, "ci", ".github", "workflows", "ci.yml"
    )
    with open(path) as f:
        workflow = yaml.safe_load(f)
    jobs = workflow["jobs"]
    assert "test" in jobs
    assert "build" in jobs
    assert "validate-manifests" in jobs
    test_steps = " ".join(str(s) for s in jobs["test"]["steps"])
    assert "pytest" in test_steps


def test_jenkinsfile_contains_expected_stages():
    with open(os.path.join(PROJECT_ROOT, "ci", "Jenkinsfile")) as f:
        content = f.read()
    for stage in ("Test", "Build", "Validate Manifests"):
        assert f"stage('{stage}')" in content
    assert "pytest" in content
    assert "docker build" in content


def test_dockerfile_has_healthcheck_and_nonroot_user():
    with open(os.path.join(PROJECT_ROOT, "docker", "Dockerfile")) as f:
        content = f.read()
    assert "HEALTHCHECK" in content
    assert "/health" in content
    assert "USER appuser" in content
    assert "useradd" in content
