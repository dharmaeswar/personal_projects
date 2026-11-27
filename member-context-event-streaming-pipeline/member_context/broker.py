"""In-memory Kafka-style broker.

Models the Kafka semantics the pipeline depends on — topics, partitions,
offsets, consumer groups, committed offsets, and lag — without a real
Kafka cluster. Nothing here connects to a broker, and no production
Kafka operation is claimed. The same semantics map one-to-one onto a
real Kafka topic (e.g. ``member-events`` with key ``member_id``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .events import MemberEvent


@dataclass
class Record:
    offset: int
    partition: int
    event: MemberEvent


class Topic:
    """One topic: N partitions, append-only logs, offsets per partition."""

    def __init__(self, name: str, partitions: int = 6):
        self.name = name
        self.partitions = partitions
        self.logs: list[list[Record]] = [[] for _ in range(partitions)]

    def partition_for(self, key: str) -> int:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return int(digest, 16) % self.partitions

    def produce(self, event: MemberEvent) -> Record:
        partition = self.partition_for(event.member_id)
        log = self.logs[partition]
        record = Record(offset=len(log), partition=partition, event=event)
        log.append(record)
        return record

    def fetch(self, partition: int, offset: int, max_records: int = 100) -> list[Record]:
        return self.logs[partition][offset : offset + max_records]

    def latest_offset(self, partition: int) -> int:
        return len(self.logs[partition])

    def total_records(self) -> int:
        return sum(len(log) for log in self.logs)


class ConsumerGroup:
    """A consumer group with committed offsets per topic-partition."""

    def __init__(self, group_id: str):
        self.group_id = group_id
        self.committed: dict[tuple[str, int], int] = {}

    def commit(self, topic: str, partition: int, offset: int) -> None:
        self.committed[(topic, partition)] = offset

    def committed_offset(self, topic: str, partition: int) -> int:
        return self.committed.get((topic, partition), 0)

    def lag(self, topic: Topic) -> dict[int, int]:
        """Per-partition lag: latest offset minus committed offset."""
        return {
            p: topic.latest_offset(p) - self.committed_offset(topic.name, p)
            for p in range(topic.partitions)
        }

    def total_lag(self, topic: Topic) -> int:
        return sum(self.lag(topic).values())


class InMemoryBroker:
    """A broker holding topics. The pipeline's producer/consumer use this."""

    def __init__(self):
        self.topics: dict[str, Topic] = {}

    def create_topic(self, name: str, partitions: int = 6) -> Topic:
        topic = Topic(name, partitions)
        self.topics[name] = topic
        return topic

    def topic(self, name: str) -> Topic:
        return self.topics[name]
