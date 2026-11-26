"""In-memory model of a Kafka-style event-streaming cluster.

Local simulation only: no real Kafka, MSK or AWS service is called.
A broker holds topics; each topic has partitions spread across
availability zones; producers append records, consumers read by offset,
and consumer groups track committed offsets so lag can be measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Record:
    key: str
    value: str
    offset: int
    partition: int


@dataclass
class Partition:
    index: int
    replicas: list[str]  # broker ids, first is leader
    records: list[Record] = field(default_factory=list)

    @property
    def leader(self) -> str:
        return self.replicas[0]

    @property
    def in_sync_replicas(self) -> list[str]:
        return list(self.replicas)

    def is_under_replicated(self, down_brokers: set[str]) -> bool:
        live = [b for b in self.replicas if b not in down_brokers]
        return len(live) < len(self.replicas)


@dataclass
class Topic:
    name: str
    partitions: list[Partition]
    retention_hours: int = 168

    def partition_for(self, key: str) -> Partition:
        return self.partitions[hash(key) % len(self.partitions)]


class BrokerCluster:
    """A small multi-broker, multi-AZ streaming cluster."""

    def __init__(self, broker_ids: list[str], zones: dict[str, str]):
        if len(broker_ids) < 3:
            raise ValueError("need at least 3 brokers for replication")
        self.broker_ids = list(broker_ids)
        self.zones = dict(zones)  # broker id -> AZ
        self.topics: dict[str, Topic] = {}
        self.down: set[str] = set()
        self.groups: dict[str, dict[str, dict[int, int]]] = {}
        # group -> topic -> partition index -> committed offset

    def create_topic(self, name: str, partitions: int,
                     replication_factor: int = 3,
                     retention_hours: int = 168) -> Topic:
        if name in self.topics:
            raise ValueError(f"topic {name!r} already exists")
        if replication_factor > len(self.broker_ids):
            raise ValueError("replication factor exceeds broker count")
        if partitions < 1:
            raise ValueError("need at least 1 partition")
        parts = []
        for i in range(partitions):
            # Round-robin replica placement across brokers and zones.
            replicas = [self.broker_ids[(i + r) % len(self.broker_ids)]
                        for r in range(replication_factor)]
            parts.append(Partition(index=i, replicas=replicas))
        topic = Topic(name=name, partitions=parts,
                      retention_hours=retention_hours)
        self.topics[name] = topic
        return topic

    def produce(self, topic_name: str, key: str, value: str) -> Record:
        topic = self.topics[topic_name]
        part = topic.partition_for(key)
        if part.leader in self.down:
            raise RuntimeError(
                f"leader broker {part.leader} is down for "
                f"{topic_name} partition {part.index}")
        record = Record(key=key, value=value,
                        offset=len(part.records), partition=part.index)
        part.records.append(record)
        return record

    def consume(self, topic_name: str, group: str, max_records: int = 10,
                commit: bool = True) -> list[Record]:
        topic = self.topics[topic_name]
        committed = self.groups.setdefault(group, {}).setdefault(topic_name, {})
        out: list[Record] = []
        for part in topic.partitions:
            start = committed.get(part.index, 0)
            for record in part.records[start:start + max_records]:
                out.append(record)
            if commit and out:
                committed[part.index] = start + len(
                    [r for r in out if r.partition == part.index])
        return out

    def lag(self, topic_name: str, group: str) -> dict[int, int]:
        topic = self.topics[topic_name]
        committed = self.groups.get(group, {}).get(topic_name, {})
        return {p.index: len(p.records) - committed.get(p.index, 0)
                for p in topic.partitions}

    def total_lag(self, topic_name: str, group: str) -> int:
        return sum(self.lag(topic_name, group).values())

    def mark_down(self, broker_id: str) -> None:
        if broker_id not in self.broker_ids:
            raise ValueError(f"unknown broker {broker_id!r}")
        self.down.add(broker_id)

    def mark_up(self, broker_id: str) -> None:
        self.down.discard(broker_id)

    def under_replicated_partitions(self) -> list[tuple[str, int]]:
        out = []
        for name, topic in self.topics.items():
            for part in topic.partitions:
                if part.is_under_replicated(self.down):
                    out.append((name, part.index))
        return out

    def leaderless_partitions(self) -> list[tuple[str, int]]:
        out = []
        for name, topic in self.topics.items():
            for part in topic.partitions:
                if part.leader in self.down:
                    out.append((name, part.index))
        return out
