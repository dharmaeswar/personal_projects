"""NoSQL / distributed-datastore health checks for the Platform Ops
Automation demo project.

Evaluates a synthetic multi-node datastore cluster (the shape of an
Aerospike / MongoDB / Kafka-style deployment: nodes, replication lag,
read latency, throughput) from plain dicts. Demo data only — no real
cluster is described, and no production NoSQL operating experience is
claimed. The Trade Desk posting for this role says NoSQL operational
experience is not required and that they train new hires; this module
is a study of the checks such a role runs.
"""

DEFAULT_MAX_REPLICATION_LAG_MS = 500
DEFAULT_MAX_P99_READ_MS = 10
DEFAULT_MIN_NODES_UP = 3


def check_cluster(nodes, capacity_qps=75_000_000,
                  max_replication_lag_ms=DEFAULT_MAX_REPLICATION_LAG_MS,
                  max_p99_read_ms=DEFAULT_MAX_P99_READ_MS,
                  min_nodes_up=DEFAULT_MIN_NODES_UP):
    """Check each cluster health item. `nodes` is a list of dicts with
    `name`, `up` (bool), `replication_lag_ms`, `p99_read_ms`, `qps`.
    Returns a list of check dicts with `name`, `status` ("pass"/"fail")
    and a human-readable `detail`."""
    checks = []
    up = [n for n in nodes if n["up"]]
    checks.append(
        {
            "name": "quorum",
            "status": "pass" if len(up) >= min_nodes_up else "fail",
            "detail": f"{len(up)} of {len(nodes)} nodes up "
            f"(minimum {min_nodes_up})",
        }
    )
    for node in nodes:
        if not node["up"]:
            checks.append(
                {
                    "name": f"node-up:{node['name']}",
                    "status": "fail",
                    "detail": f"node {node['name']} is down",
                }
            )
            continue
        checks.append(
            {
                "name": f"node-up:{node['name']}",
                "status": "pass",
                "detail": f"node {node['name']} is up",
            }
        )
        checks.append(
            {
                "name": f"replication-lag:{node['name']}",
                "status": "pass"
                if node["replication_lag_ms"] <= max_replication_lag_ms
                else "fail",
                "detail": f"node {node['name']} replication lag "
                f"{node['replication_lag_ms']} ms "
                f"(limit {max_replication_lag_ms})",
            }
        )
        checks.append(
            {
                "name": f"p99-read:{node['name']}",
                "status": "pass"
                if node["p99_read_ms"] <= max_p99_read_ms
                else "fail",
                "detail": f"node {node['name']} p99 read "
                f"{node['p99_read_ms']} ms (limit {max_p99_read_ms})",
            }
        )
    total_qps = sum(n["qps"] for n in up)
    checks.append(
        {
            "name": "throughput-headroom",
            "status": "pass" if total_qps <= capacity_qps else "fail",
            "detail": f"cluster throughput {total_qps:,} qps "
            f"(capacity {capacity_qps:,} qps)",
        }
    )
    return checks


def cluster_summary(nodes, capacity_qps=75_000_000):
    """Aggregate a cluster into one summary dict."""
    checks = check_cluster(nodes, capacity_qps=capacity_qps)
    failed = [c for c in checks if c["status"] == "fail"]
    up = [n for n in nodes if n["up"]]
    return {
        "nodes_up": len(up),
        "nodes_total": len(nodes),
        "total_qps": sum(n["qps"] for n in up),
        "max_replication_lag_ms": max(
            (n["replication_lag_ms"] for n in up), default=0
        ),
        "max_p99_read_ms": max((n["p99_read_ms"] for n in up), default=0),
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "overall": "healthy" if not failed else "degraded",
    }


def demo_nodes():
    """A synthetic 5-node cluster: 4 healthy nodes and 1 node whose
    replication lag is over the limit, so the demo shows a failure."""
    return [
        {"name": "node-a", "up": True, "replication_lag_ms": 120,
         "p99_read_ms": 0.8, "qps": 14_000_000},
        {"name": "node-b", "up": True, "replication_lag_ms": 95,
         "p99_read_ms": 0.7, "qps": 15_000_000},
        {"name": "node-c", "up": True, "replication_lag_ms": 640,
         "p99_read_ms": 1.4, "qps": 13_000_000},
        {"name": "node-d", "up": True, "replication_lag_ms": 110,
         "p99_read_ms": 0.9, "qps": 16_000_000},
        {"name": "node-e", "up": True, "replication_lag_ms": 88,
         "p99_read_ms": 0.6, "qps": 14_000_000},
    ]


def health_report(nodes, capacity_qps=75_000_000):
    """One-line-per-check text report for a synthetic cluster."""
    summary = cluster_summary(nodes, capacity_qps=capacity_qps)
    lines = [
        f"NoSQL cluster: {summary['overall']} "
        f"({summary['checks_passed']}/{summary['checks_total']} checks pass)",
        f"Nodes up: {summary['nodes_up']}/{summary['nodes_total']}, "
        f"throughput {summary['total_qps']:,} qps, "
        f"max replication lag {summary['max_replication_lag_ms']} ms, "
        f"max p99 read {summary['max_p99_read_ms']} ms",
    ]
    for check in check_cluster(nodes, capacity_qps=capacity_qps):
        mark = "PASS" if check["status"] == "pass" else "FAIL"
        lines.append(f"[{mark}] {check['name']}: {check['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(health_report(demo_nodes()))
