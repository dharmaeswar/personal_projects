"""End-to-end demo: users in the store, tasks through the queue, cache in KV.

Run:  python run_demo.py
Shows one full flow: seed users + events (D1-style store), enqueue
processing tasks (Queues-style), a worker leases and acks them, results
are cached in KV with a TTL, and metrics + alerts are printed at the end.
"""

from edgeprimitives import DurableStore, KeyValueStore, MessageQueue, Metrics
from edgeprimitives.monitoring import AlertRule, evaluate_alerts


def main() -> dict:
    metrics = Metrics()
    store = DurableStore()
    queue = MessageQueue()
    kv = KeyValueStore()

    # Seed: two users and one event each in the durable store.
    ada = store.create_user("ada@example.com", "Ada")
    grace = store.create_user("grace@example.com", "Grace")
    store.record_event(ada, "signup", '{"plan": "free"}')
    store.record_event(grace, "signup", '{"plan": "pro"}')

    # Enqueue one processing task per event.
    for event in store.user_events(ada) + store.user_events(grace):
        queue.enqueue({"event_id": event["id"], "kind": event["kind"]})

    # Worker: lease, "process" (count events per kind), ack, cache the result.
    processed = 0
    for task in queue.lease(batch_size=10):
        counts = {row["kind"]: row["n"] for row in store.event_counts_by_kind()}
        kv.put("stats:event_counts", str(counts), ttl_s=300, metadata={"source": "worker"})
        queue.ack(task["id"])
        processed += 1
        metrics.record("process_task", 1.5)

    alerts = evaluate_alerts(
        metrics,
        [AlertRule("queue-backlog", "queue.depth", 0.0)],
        {"queue.depth": float(queue.depth())},
    )
    result = {
        "users": 2,
        "events": 2,
        "processed": processed,
        "queue_depth": queue.depth(),
        "dead_letters": queue.dead_letter_count(),
        "cached_stats": kv.get("stats:event_counts"),
        "metrics": metrics.summary(),
        "alerts": alerts,
    }
    print(result)
    return result


if __name__ == "__main__":
    main()
