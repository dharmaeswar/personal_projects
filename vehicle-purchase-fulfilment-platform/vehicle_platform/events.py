"""Kafka-style append-only event log, modelled in memory.

Topics are partitioned by key hash; each record carries a
per-partition offset. Consumer groups track committed offsets per
partition. Events that fail validation go to the dead-letter queue
instead of the topic. This is a local model of the pattern, not a
Kafka client: no broker is contacted.
"""

from __future__ import annotations

import hashlib
import json


class EventError(ValueError):
    """Raised for invalid topics, keys, or event payloads."""


def partition_for(key: str, n_partitions: int) -> int:
    """Deterministic partition assignment, like Kafka's default."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % n_partitions


class EventLog:
    def __init__(self, topics: dict[str, int] | None = None):
        # topic -> number of partitions
        self.topics = dict(topics or {"order-events": 3, "vehicle-events": 2})
        self._records: dict[str, list[list[dict]]] = {
            topic: [[] for _ in range(n)]
            for topic, n in self.topics.items()
        }
        self._committed: dict[str, dict[int, int]] = {}
        self.dlq: list[dict] = []

    def publish(self, topic: str, key: str, payload: dict) -> dict:
        """Append one event; returns the stored record with its offset."""
        if topic not in self.topics:
            raise EventError(f"unknown topic: {topic}")
        if not isinstance(key, str) or not key:
            raise EventError("event key is required")
        if not isinstance(payload, dict) or "type" not in payload:
            self.dlq.append(
                {"topic": topic, "key": key, "payload": payload,
                 "reason": "payload missing event type"}
            )
            raise EventError("payload missing event type; sent to DLQ")
        partition = partition_for(key, self.topics[topic])
        records = self._records[topic][partition]
        record = {
            "topic": topic,
            "partition": partition,
            "offset": len(records),
            "key": key,
            "payload": payload,
        }
        records.append(record)
        return record

    def read(self, topic: str, partition: int, offset: int = 0) -> list[dict]:
        """Read records from a partition starting at an offset."""
        if topic not in self.topics:
            raise EventError(f"unknown topic: {topic}")
        if not 0 <= partition < self.topics[topic]:
            raise EventError(f"bad partition {partition} for {topic}")
        return list(self._records[topic][partition][offset:])

    def read_key(self, topic: str, key: str) -> list[dict]:
        """All records for one key, in offset order."""
        partition = partition_for(key, self.topics[topic])
        return [r for r in self._records[topic][partition] if r["key"] == key]

    def commit(self, group: str, topic: str, partition: int, offset: int) -> None:
        """Record a consumer group's committed offset for a partition."""
        self._committed.setdefault(group, {})[(topic, partition)] = offset

    def committed(self, group: str, topic: str, partition: int) -> int:
        return self._committed.get(group, {}).get((topic, partition), -1)

    def lag(self, group: str, topic: str, partition: int) -> int:
        """Unconsumed records for a group on one partition."""
        latest = len(self._records[topic][partition]) - 1
        return max(0, latest - self.committed(group, topic, partition))

    def to_json(self) -> str:
        return json.dumps(
            {"topics": self.topics, "records": self._records, "dlq": self.dlq},
            indent=2,
            sort_keys=True,
        )
