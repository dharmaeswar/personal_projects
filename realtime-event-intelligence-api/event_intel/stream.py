"""In-memory streaming topic with partitions, offsets and consumer groups.

Modelled on a Kafka topic: producers publish records to a partition,
consumers read in offset order and commit offsets per consumer group.
All state is in memory; nothing here talks to a real broker.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Record:
    partition: int
    offset: int
    key: str
    value: dict


class StreamTopic:
    """A topic with a fixed number of partitions and per-group offsets."""

    def __init__(self, name: str, partitions: int = 3):
        if partitions < 1:
            raise ValueError("partitions must be >= 1")
        self.name = name
        self.partitions = partitions
        self._lock = threading.Lock()
        self._logs: list[list[Record]] = [[] for _ in range(partitions)]
        # group -> partition -> next offset to read
        self._committed: dict[str, dict[int, int]] = {}

    def _partition_for(self, key: str) -> int:
        return sum(key.encode("utf-8")) % self.partitions

    def publish(self, key: str, value: dict) -> Record:
        """Append one record; returns it with its partition and offset."""
        partition = self._partition_for(key)
        with self._lock:
            offset = len(self._logs[partition])
            record = Record(partition=partition, offset=offset, key=key, value=value)
            self._logs[partition].append(record)
            return record

    def poll(self, group: str, max_records: int = 100) -> list[Record]:
        """Read uncommitted records for a consumer group, in offset order."""
        out: list[Record] = []
        with self._lock:
            offsets = self._committed.setdefault(group, {p: 0 for p in range(self.partitions)})
            for partition in range(self.partitions):
                start = offsets[partition]
                for record in self._logs[partition][start:]:
                    if len(out) >= max_records:
                        return out
                    out.append(record)
        return out

    def commit(self, group: str, records: list[Record]) -> None:
        """Advance the group's committed offset past the given records."""
        with self._lock:
            offsets = self._committed.setdefault(group, {p: 0 for p in range(self.partitions)})
            for record in records:
                offsets[record.partition] = max(offsets[record.partition], record.offset + 1)

    def committed_offset(self, group: str, partition: int) -> int:
        with self._lock:
            return self._committed.get(group, {}).get(partition, 0)

    def lag(self, group: str) -> int:
        """Total unread records for a group across all partitions."""
        with self._lock:
            offsets = self._committed.get(group, {})
            return sum(
                len(self._logs[p]) - offsets.get(p, 0) for p in range(self.partitions)
            )
