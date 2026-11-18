"""Streaming-style ingest, modelled on event-stream concepts.

This is an in-memory simulation of the consume/commit pattern a streaming
job uses (the same shape as a Kafka consumer: topics, offsets, at-least-once
delivery with replay from the last committed offset). It uses no streaming
library and connects to no broker — the point is to show the offset,
batching, and late-data handling logic, not to run a cluster.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConsumerRecord:
    offset: int
    value: dict


@dataclass
class EventConsumer:
    """A minimal in-memory event-stream consumer.

    ``produce`` appends records to the topic. ``poll`` returns the next
    batch without advancing the committed offset; ``commit`` marks the
    batch processed. If the process stops before committing, the next
    ``poll`` re-delivers the same records — at-least-once delivery.
    """

    topic: str = "ad_events"
    _log: list[dict] = field(default_factory=list)
    _next_offset: int = 0
    committed_offset: int = 0

    def produce(self, records: list[dict]) -> int:
        """Append records to the topic; return the offset of the first one."""
        first = self._next_offset
        for record in records:
            self._log.append(record)
            self._next_offset += 1
        return first

    def poll(self, max_records: int = 100) -> list[ConsumerRecord]:
        """Return up to ``max_records`` records from the committed offset."""
        batch = self._log[self.committed_offset : self.committed_offset + max_records]
        return [
            ConsumerRecord(offset=self.committed_offset + i, value=record)
            for i, record in enumerate(batch)
        ]

    def commit(self, records: list[ConsumerRecord]) -> None:
        """Mark ``records`` processed: advance the committed offset past them."""
        if not records:
            return
        last = records[-1].offset
        if last + 1 > self.committed_offset:
            self.committed_offset = last + 1

    @property
    def pending(self) -> int:
        """Records produced but not yet committed."""
        return len(self._log) - self.committed_offset

    @property
    def size(self) -> int:
        return len(self._log)


def consume_all_in_batches(
    consumer: EventConsumer, batch_size: int = 100
) -> list[dict]:
    """Drain the topic in batches, committing each batch; return all records."""
    out: list[dict] = []
    while consumer.pending > 0:
        batch = consumer.poll(batch_size)
        if not batch:
            break
        out.extend(record.value for record in batch)
        consumer.commit(batch)
    return out
