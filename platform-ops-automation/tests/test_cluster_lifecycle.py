"""Tests for ops.cluster_lifecycle — Kubernetes cluster lifecycle checks.

Synthetic inputs only; no real cluster is contacted.
"""

from ops.cluster_lifecycle import (
    MAX_MINOR_SKEW,
    check_namespace_policies,
    check_pod_policy,
    check_upgrade_readiness,
    drain_is_safe,
    generate_synthetic_cluster,
    namespace_capacity,
    parse_cpu,
    parse_memory,
    parse_version,
    summarize_upgrade,
    version_skew_ok,
)


def test_parse_version():
    assert parse_version("v1.31.2") == (1, 31, 2)
    assert parse_version("1.28") == (1, 28, 0)
    assert parse_version("v1.31") == (1, 31, 0)
    assert parse_version("not-a-version") is None
    assert parse_version(None) is None


def test_version_skew_ok_within_limit():
    assert version_skew_ok("v1.31.2", "v1.31.1")["ok"] is True
    assert version_skew_ok("v1.31.2", "v1.28.0")["ok"] is True  # exactly 3 behind


def test_version_skew_too_far_behind():
    result = version_skew_ok("v1.31.2", "v1.27.0")
    assert result["ok"] is False
    assert "4 minor versions" in result["reason"]


def test_version_skew_kubelet_newer_blocked():
    result = version_skew_ok("v1.31.2", "v1.32.0")
    assert result["ok"] is False
    assert "newer" in result["reason"]


def test_version_skew_major_mismatch():
    assert version_skew_ok("v1.31.2", "v2.31.2")["ok"] is False
    assert version_skew_ok("v1.31.2", "bad")["ok"] is False


def test_drain_is_safe():
    assert drain_is_safe(3, 2)["safe"] is True
    assert drain_is_safe(2, 2)["safe"] is False
    assert drain_is_safe(3, 2, draining=2)["safe"] is False


def test_upgrade_readiness_clean_cluster():
    cluster = {
        "control_plane_version": "v1.31.2",
        "target_version": "v1.32.0",
        "nodes": [{"name": "n1", "version": "v1.31.0", "ready": True}],
        "workloads": [
            {"name": "web", "namespace": "default", "replicas": 3,
             "min_available": 2, "uses_removed_api": False}
        ],
    }
    report = check_upgrade_readiness(cluster)
    assert report["ready"] is True
    assert report["blockers"] == []
    assert summarize_upgrade(report).startswith("ready to upgrade")


def test_upgrade_readiness_blocks_on_not_ready_node():
    cluster = {
        "control_plane_version": "v1.31.2",
        "target_version": "v1.32.0",
        "nodes": [{"name": "n1", "version": "v1.31.0", "ready": False}],
        "workloads": [],
    }
    report = check_upgrade_readiness(cluster)
    assert report["ready"] is False
    assert any("not Ready" in b for b in report["blockers"])


def test_upgrade_readiness_blocks_on_removed_api():
    cluster = {
        "control_plane_version": "v1.31.2",
        "target_version": "v1.32.0",
        "nodes": [{"name": "n1", "version": "v1.31.0", "ready": True}],
        "workloads": [
            {"name": "old", "namespace": "default", "replicas": 2,
             "min_available": 1, "uses_removed_api": True}
        ],
    }
    report = check_upgrade_readiness(cluster)
    assert report["ready"] is False
    assert any("removed" in b for b in report["blockers"])


def test_upgrade_readiness_drain_unsafe_is_warning_not_blocker():
    cluster = {
        "control_plane_version": "v1.31.2",
        "target_version": "v1.32.0",
        "nodes": [{"name": "n1", "version": "v1.31.0", "ready": True}],
        "workloads": [
            {"name": "tight", "namespace": "default", "replicas": 2,
             "min_available": 2, "uses_removed_api": False}
        ],
    }
    report = check_upgrade_readiness(cluster)
    assert report["ready"] is True
    assert len(report["warnings"]) == 1
    assert "drain unsafe" in report["warnings"][0]


def test_synthetic_cluster_has_blockers():
    cluster = generate_synthetic_cluster()
    report = check_upgrade_readiness(cluster)
    assert report["ready"] is False
    # node-b at v1.28.0 is exactly 3 minor behind v1.31.2, so skew is NOT a blocker;
    # blockers are the not-Ready node and the removed-API workload.
    assert len(report["blockers"]) == 2
    assert any("not Ready" in b for b in report["blockers"])
    assert any("removed" in b for b in report["blockers"])
    assert len(report["warnings"]) == 1  # drain-unsafe batch worker


def _good_pod():
    return {
        "name": "web",
        "namespace": "default",
        "default_deny_policy": True,
        "containers": [
            {"name": "web", "image": "web:v1.0.0", "run_as_root": False,
             "resources": {"limits": {"cpu": "500m", "memory": "512Mi"}}}
        ],
    }


def test_pod_policy_compliant():
    assert check_pod_policy(_good_pod()) == []


def test_pod_policy_missing_default_deny():
    pod = _good_pod()
    pod["default_deny_policy"] = False
    violations = check_pod_policy(pod)
    assert any(v["rule"] == "default-deny-network-policy" for v in violations)


def test_pod_policy_root_and_latest_and_no_limits():
    pod = _good_pod()
    pod["containers"] = [
        {"name": "bad", "image": "bad:latest", "run_as_root": True,
         "resources": {"limits": {}}}
    ]
    rules = {v["rule"] for v in check_pod_policy(pod)}
    assert rules == {"no-root-user", "resource-limits-required", "no-latest-tag"}


def test_namespace_policies_report():
    report = check_namespace_policies([_good_pod()])
    assert report["compliant"] is True
    bad = _good_pod()
    bad["name"] = "bad-pod"
    bad["containers"][0]["run_as_root"] = True
    report = check_namespace_policies([_good_pod(), bad])
    assert report["compliant"] is False
    assert "bad-pod" in report["violations"]


def test_parse_cpu_and_memory():
    assert parse_cpu("100m") == 100.0
    assert parse_cpu("2") == 2000.0
    assert parse_cpu("0.5") == 500.0
    assert parse_memory("128Mi") == 128.0
    assert parse_memory("1Gi") == 1024.0
    assert parse_memory("512M") == 512.0


def test_namespace_capacity_headroom():
    report = namespace_capacity(
        [
            {"name": "default", "cpu_requests": "2500m", "memory_requests": "8Gi"},
            {"name": "batch", "cpu_requests": "1500m", "memory_requests": "4Gi"},
        ],
        {"cpu": "8000m", "memory": "32Gi"},
    )
    assert report["total_cpu_m"] == 4000.0
    assert report["cpu_headroom_pct"] == 50.0
    assert report["memory_headroom_pct"] == 62.5
    assert report["scale_out"] is False
    assert report["namespaces"][0]["cpu_pct"] == 31.25


def test_namespace_capacity_scale_out_below_20_headroom():
    report = namespace_capacity(
        [{"name": "busy", "cpu_requests": "7500m", "memory_requests": "30Gi"}],
        {"cpu": "8000m", "memory": "32Gi"},
    )
    assert report["scale_out"] is True
    assert report["cpu_headroom_pct"] == 6.2


def test_max_minor_skew_constant():
    assert MAX_MINOR_SKEW == 3
