"""Tests for ops/nosql_health.py (demo project)."""

from ops.nosql_health import (
    check_cluster,
    cluster_summary,
    demo_nodes,
    health_report,
)


def _healthy_nodes():
    return [
        {"name": "node-a", "up": True, "replication_lag_ms": 120,
         "p99_read_ms": 0.8, "qps": 14_000_000},
        {"name": "node-b", "up": True, "replication_lag_ms": 95,
         "p99_read_ms": 0.7, "qps": 15_000_000},
        {"name": "node-c", "up": True, "replication_lag_ms": 110,
         "p99_read_ms": 0.9, "qps": 16_000_000},
    ]


def _statuses(checks):
    return {c["name"]: c["status"] for c in checks}


def test_healthy_cluster_passes_all():
    assert cluster_summary(_healthy_nodes())["overall"] == "healthy"
    assert cluster_summary(_healthy_nodes())["nodes_up"] == 3
    assert cluster_summary(_healthy_nodes())["total_qps"] == 45_000_000


def test_replication_lag_failure_flagged():
    nodes = _healthy_nodes()
    nodes[1]["replication_lag_ms"] = 900
    assert _statuses(check_cluster(nodes))["replication-lag:node-b"] == "fail"
    assert cluster_summary(nodes)["overall"] == "degraded"
    assert cluster_summary(nodes)["max_replication_lag_ms"] == 900


def test_p99_latency_failure_flagged():
    nodes = _healthy_nodes()
    nodes[0]["p99_read_ms"] = 25
    assert _statuses(check_cluster(nodes))["p99-read:node-a"] == "fail"


def test_down_node_breaks_quorum():
    nodes = _healthy_nodes()
    nodes[0]["up"] = False
    nodes[1]["up"] = False
    statuses = _statuses(check_cluster(nodes))
    assert statuses["quorum"] == "fail"
    assert statuses["node-up:node-a"] == "fail"
    assert cluster_summary(nodes)["nodes_up"] == 1


def test_throughput_over_capacity_fails():
    nodes = _healthy_nodes()
    assert _statuses(
        check_cluster(nodes, capacity_qps=40_000_000)
    )["throughput-headroom"] == "fail"


def test_demo_nodes_show_one_lag_failure():
    summary = cluster_summary(demo_nodes())
    assert summary["overall"] == "degraded"
    assert summary["max_replication_lag_ms"] == 640
    assert summary["checks_passed"] == summary["checks_total"] - 1
    report = health_report(demo_nodes())
    assert "degraded" in report
    assert "replication-lag:node-c" in report
