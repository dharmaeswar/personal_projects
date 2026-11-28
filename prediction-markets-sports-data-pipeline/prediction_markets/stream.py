"""Kafka-style event stream, simulated in-process.

A real deployment would use Kafka topics; this module mirrors the
producer/consumer contract without a broker so the pipeline runs anywhere:
an append-only log with per-record offsets, a consumer that commits
offsets, and replay from a committed offset. Consumers dedupe by the
record key (event, book, timestamp), giving at-least-once delivery with
exactly-once effect — the same guarantee the pipeline relies on in
``cleanse``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ingest import Snapshot


@dataclass
class StreamRecord:
    offset: int
    key: str
    value: Snapshot


class Topic:
    """Append-only log for one feed."""

    def __init__(self, name: str):
        self.name = name
        self._log: list[StreamRecord] = []

    def produce(self, snapshot: Snapshot) -> int:
        key = f"{snapshot.event_id}|{snapshot.book}|{snapshot.ts.isoformat()}"
        offset = len(self._log)
        self._log.append(StreamRecord(offset, key, snapshot))
        return offset

    def read_from(self, offset: int) -> list[StreamRecord]:
        return [r for r in self._log if r.offset >= offset]

    def __len__(self) -> int:
        return len(self._log)


class Consumer:
    """Offset-committing consumer with key-based dedupe."""

    def __init__(self, topic: Topic, group: str):
        self.topic = topic
        self.group = group
        self.committed_offset = 0
        self.seen_keys: set[str] = set()
        self.delivered: list[Snapshot] = []

    def poll(self) -> list[Snapshot]:
        fresh: list[Snapshot] = []
        for rec in self.topic.read_from(self.committed_offset):
            if rec.key in self.seen_keys:
                continue
            self.seen_keys.add(rec.key)
            self.delivered.append(rec.value)
            fresh.append(rec.value)
        if self.topic._log:
            self.committed_offset = self.topic._log[-1].offset + 1
        return fresh

    def replay_from(self, offset: int) -> list[Snapshot]:
        """Re-read from an offset; dedupe keeps the effect exactly-once."""
        replayed: list[Snapshot] = []
        for rec in self.topic.read_from(offset):
            if rec.key in self.seen_keys:
                continue
            self.seen_keys.add(rec.key)
            self.delivered.append(rec.value)
            replayed.append(rec.value)
        return replayed
