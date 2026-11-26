"""Platform health, capacity and alerting for the messaging platform.

Health is computed from a live :class:`BrokerCluster` plus the queues
on the event bus: under-replicated partitions, leaderless partitions,
consumer lag, queue depth and dead-letter depth. Alerts are plain
dicts with a severity so an on-call runbook can act on them.
"""

from __future__ import annotations

from .brokers import BrokerCluster
from .routing import EventBus

DEFAULT_LAG_WARN = 1_000
DEFAULT_LAG_CRITICAL = 10_000
DEFAULT_QUEUE_WARN = 5_000


def health_snapshot(cluster: BrokerCluster, bus: EventBus,
                    groups: dict[str, str]) -> dict:
    """groups maps consumer-group name -> topic name."""
    lag_by_group = {}
    for group, topic in groups.items():
        lag_by_group[group] = {
            "per_partition": cluster.lag(topic, group),
            "total": cluster.total_lag(topic, group),
        }
    return {
        "brokers_total": len(cluster.broker_ids),
        "brokers_down": sorted(cluster.down),
        "under_replicated_partitions": cluster.under_replicated_partitions(),
        "leaderless_partitions": cluster.leaderless_partitions(),
        "consumer_lag": lag_by_group,
        "queue_depths": {name: len(q.messages)
                         for name, q in bus.queues.items()},
        "dead_letter_depths": {
            name: len(q.dead_letter.messages)
            for name, q in bus.queues.items() if q.dead_letter is not None},
    }


def evaluate_alerts(snapshot: dict, lag_warn: int = DEFAULT_LAG_WARN,
                    lag_critical: int = DEFAULT_LAG_CRITICAL,
                    queue_warn: int = DEFAULT_QUEUE_WARN) -> list[dict]:
    alerts = []
    for broker in snapshot["brokers_down"]:
        alerts.append({"severity": "critical",
                       "rule": "broker_down",
                       "detail": f"broker {broker} is down"})
    for topic, part in snapshot["leaderless_partitions"]:
        alerts.append({"severity": "critical",
                       "rule": "leaderless_partition",
                       "detail": f"{topic} partition {part} has no live leader"})
    for topic, part in snapshot["under_replicated_partitions"]:
        alerts.append({"severity": "warning",
                       "rule": "under_replicated_partition",
                       "detail": f"{topic} partition {part} is under-replicated"})
    for group, lag in snapshot["consumer_lag"].items():
        total = lag["total"]
        if total >= lag_critical:
            alerts.append({"severity": "critical", "rule": "consumer_lag",
                           "detail": f"group {group} lag {total} >= "
                                     f"{lag_critical}"})
        elif total >= lag_warn:
            alerts.append({"severity": "warning", "rule": "consumer_lag",
                           "detail": f"group {group} lag {total} >= "
                                     f"{lag_warn}"})
    for name, depth in snapshot["queue_depths"].items():
        if depth >= queue_warn:
            alerts.append({"severity": "warning", "rule": "queue_depth",
                           "detail": f"queue {name} depth {depth} >= "
                                     f"{queue_warn}"})
    for name, depth in snapshot["dead_letter_depths"].items():
        if depth > 0:
            alerts.append({"severity": "warning", "rule": "dead_letter",
                           "detail": f"queue {name} has {depth} message(s) "
                                     f"in its dead-letter queue"})
    return alerts


def capacity_report(cluster: BrokerCluster) -> dict:
    """Per-topic stored-record counts and partition balance."""
    report = {}
    for name, topic in cluster.topics.items():
        counts = [len(p.records) for p in topic.partitions]
        total = sum(counts)
        report[name] = {
            "partitions": len(topic.partitions),
            "records": total,
            "max_partition_records": max(counts) if counts else 0,
            "min_partition_records": min(counts) if counts else 0,
            "skew": (max(counts) - min(counts)) if counts else 0,
        }
    return report
