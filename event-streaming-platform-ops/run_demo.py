"""End-to-end demo: build the platform from iac/platform.yaml, produce
synthetic order events, route them, consume them, fail an AZ, and
print the health + DR report.

All data is synthetic (seeded order ids). No AWS service is called.
Run:  python run_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from messaging import (BrokerCluster, EventBus, Queue, Rule,
                       capacity_report, check_acls, check_tls_config,
                       dr_readiness, evaluate_alerts, health_snapshot,
                       load_yaml_manifest, patch_readiness_report,
                       restore_az, simulate_az_failure, triage_findings,
                       validate_patch_plan, validate_platform_manifest)

HERE = os.path.dirname(os.path.abspath(__file__))


def build_platform():
    manifest = load_yaml_manifest(os.path.join(HERE, "iac", "platform.yaml"))
    errors = validate_platform_manifest(manifest)
    if errors:
        raise SystemExit("manifest invalid:\n" + "\n".join(errors))
    zones = {b["id"]: b["availability_zone"]
             for b in manifest["cluster"]["brokers"]}
    cluster = BrokerCluster(list(zones), zones)
    for topic in manifest["topics"]:
        cluster.create_topic(topic["name"], topic["partitions"],
                             topic["replication_factor"],
                             topic["retention_hours"])
    bus = EventBus()
    dlqs = {}
    for queue in manifest["queues"]:
        dlq = Queue(queue["dead_letter_queue"])
        dlqs[queue["name"]] = dlq
        bus.add_queue(dlq)
        bus.add_queue(Queue(queue["name"], dead_letter=dlq,
                            max_receives=3))
    bus.add_rule(Rule("high-value-orders",
                      {"source": ["com.store.orders"],
                       "detail-type": ["OrderPlaced"]},
                      ["order-notifications"]))
    bus.add_rule(Rule("inventory-low",
                      {"source": ["com.store.inventory"],
                       "detail-type": ["StockLow"]},
                      ["inventory-alerts"]))
    return cluster, bus


def main():
    cluster, bus = build_platform()
    print(f"DR readiness: {dr_readiness(cluster)}")
    produced = 0
    for i in range(120):
        cluster.produce("orders", key=f"order-{i}",
                        value=f"order {i} total {100 + i}")
        produced += 1
    print(f"Produced {produced} records to topic 'orders'")
    for i in range(12):
        bus.publish({"source": "com.store.orders",
                     "detail-type": "OrderPlaced",
                     "detail": {"order_id": f"order-{i}", "total": 100 + i}})
    bus.publish({"source": "com.store.inventory",
                 "detail-type": "StockLow",
                 "detail": {"sku": "TV-55", "on_hand": 2}})
    print("Queue depths:", {n: len(q.messages)
                            for n, q in bus.queues.items()})
    # One poison message: received 3 times, never acknowledged.
    bad = bus.queues["order-notifications"]
    bad.receive(1)
    bad.receive(1)
    bad.receive(1)
    moved = bad.redrive()
    print(f"Redrove {moved} poison message(s) to the DLQ")
    consumed = cluster.consume("orders", "fulfillment-service", 120)
    print(f"Consumed {len(consumed)} records; lag now "
          f"{cluster.total_lag('orders', 'fulfillment-service')}")
    snapshot = health_snapshot(cluster, bus,
                               {"fulfillment-service": "orders"})
    print("Alerts:", evaluate_alerts(snapshot))
    print("Capacity:", capacity_report(cluster))
    result = simulate_az_failure(cluster, "us-east-1a")
    print("AZ failure:", {k: result[k] for k in
                          ("failed_az", "brokers_down", "available",
                           "estimated_rto_minutes")})
    print(f"Promoted {len(result['promoted_partitions'])} partitions; "
          f"lost {len(result['lost_partitions'])}")
    restore_az(cluster, "us-east-1a")
    print("AZ restored; brokers down now:", sorted(cluster.down))
    # Middleware security: triage a scan, validate a CVE patch plan,
    # and check the broker TLS config and ACLs before rollout.
    findings = [
        {"cve": "CVE-2026-1001", "severity": "high",
         "component": "kafka", "status": "open"},
        {"cve": "CVE-2026-1002", "severity": "medium",
         "component": "kafka", "status": "open"},
        {"cve": "CVE-2026-1003", "severity": "low",
         "component": "zookeeper", "status": "fixed"},
    ]
    print("Scan triage:", triage_findings(findings)["by_severity"])
    plan = {"component": "kafka", "current_version": "3.7.0",
            "target_version": "3.7.1", "cves": ["CVE-2026-1001"],
            "pre_patch_checks": ["health_snapshot", "lag_zero"],
            "post_patch_checks": ["health_snapshot", "regression_suite"],
            "nonprod_validated": True, "rollback_plan": True}
    print("Patch plan blockers:", validate_patch_plan(plan))
    tls = {"tls_min_version": "1.2",
           "cipher": "TLS_AES_256_GCM_SHA384", "cert_expires_in_days": 90,
           "mutual_tls": True, "encryption_at_rest": True}
    print("TLS findings:", check_tls_config(tls))
    acls = [{"principal": "fulfillment-service", "resource": "orders",
             "permission": "read"},
            {"principal": "billing-service", "resource": "*",
             "permission": "write"}]
    print("ACL violations:",
          check_acls(acls, {"fulfillment-service", "billing-service"}))
    report = patch_readiness_report(
        plan, [{**f, "status": "fixed"} for f in findings], tls,
        [acls[0]], {"fulfillment-service"})
    print("Patch readiness: ready =", report["ready"])


if __name__ == "__main__":
    main()
