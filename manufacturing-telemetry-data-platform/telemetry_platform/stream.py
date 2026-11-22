"""Streaming ingestion modelled on a Kafka topic.

Producers publish telemetry records to a named topic; the topic is split
into partitions by machine id, records carry offsets, and consumer groups
track their own committed offset per partition. Pure Python, no broker.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Record:
    topic: str
    partition: int
    offset: int
    key: str
    value: dict


class Topic:
    """A partitioned, append-only log with consumer-group offsets."""

    def __init__(self, name: str, partitions: int = 4) -> None:
        if partitions < 1:
            raise ValueError("partitions must be >= 1")
        self.name = name
        self.partitions = partitions
        self._log: list[list[Record]] = [[] for _ in range(partitions)]
        self._committed: dict[str, dict[int, int]] = {}
        self._seq = itertools.count()

    def _partition_for(self, key: str) -> int:
        digest = hashlib.sha256(key.encode()).digest()
        return int.from_bytes(digest[:4], "big") % self.partitions

    def publish(self, key: str, value: dict) -> Record:
        partition = self._partition_for(key)
        offset = len(self._log[partition])
        record = Record(self.name, partition, offset, key, dict(value))
        self._log[partition].append(record)
        next(self._seq)
        return record

    def poll(self, group: str, max_records: int = 100) -> list[Record]:
        """Return uncommitted records for a consumer group, in offset order."""
        out: list[Record] = []
        committed = self._committed.setdefault(group, {})
        for partition in range(self.partitions):
            start = committed.get(partition, 0)
            for record in self._log[partition][start:]:
                if len(out) >= max_records:
                    return out
                out.append(record)
        return out

    def commit(self, group: str, records: list[Record]) -> None:
        committed = self._committed.setdefault(group, {})
        for record in records:
            committed[record.partition] = max(
                committed.get(record.partition, 0), record.offset + 1
            )

    def lag(self, group: str) -> int:
        committed = self._committed.get(group, {})
        total = 0
        for partition in range(self.partitions):
            total += len(self._log[partition]) - committed.get(partition, 0)
        return total

    def size(self) -> int:
        return sum(len(part) for part in self._log)
