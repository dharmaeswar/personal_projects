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
                       capacity_report, dr_readiness, evaluate_alerts,
                       health_snapshot, load_yaml_manifest, restore_az,
                       simulate_az_failure, validate_platform_manifest)

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


if __name__ == "__main__":
    main()
