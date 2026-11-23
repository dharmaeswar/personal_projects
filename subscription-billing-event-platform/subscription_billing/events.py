"""Event bus — SNS-topic / SQS-queue shaped messaging.

Topics fan out to subscribed queues. Each queue delivers FIFO per
grouping key (the subscriber id), deduplicates on the event's dedup id,
and moves a message to the dead-letter queue after ``max_receives``
failed receives. A message becomes visible again after the visibility
timeout, so a crashed handler is retried instead of losing the event.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class Event:
    event_id: str
    event_type: str  # subscription.provisioned | billing.charged | ...
    partner_id: str
    subscriber_id: str
    payload: dict
    dedup_id: str = ""
    grouping_key: str = ""  # FIFO ordering key; defaults to subscriber_id

    def __post_init__(self) -> None:
        if not self.dedup_id:
            self.dedup_id = self.event_id
        if not self.grouping_key:
            self.grouping_key = self.subscriber_id


@dataclass
class _Queued:
    event: Event
    receives: int = 0
    visible_at: float = 0.0


class Queue:
    """One SQS-shaped queue with a dead-letter queue."""

    def __init__(self, name: str, *, max_receives: int = 3,
                 visibility_timeout_s: float = 30.0) -> None:
        self.name = name
        self.max_receives = max_receives
        self.visibility_timeout_s = visibility_timeout_s
        self._pending: deque[_Queued] = deque()
        self._seen_dedup: set[str] = set()
        self.dead_letter: list[Event] = []
        # A delivered-but-not-deleted message stays queued with a future
        # visible_at; while it is in that window it blocks later messages
        # for the same grouping key (FIFO), and once the window expires it
        # is redelivered (receives counted toward the DLQ limit).

    def enqueue(self, event: Event) -> bool:
        """Return False when the event is a duplicate (already seen)."""
        if event.dedup_id in self._seen_dedup:
            return False
        self._seen_dedup.add(event.dedup_id)
        self._pending.append(_Queued(event=event))
        return True

    def receive(self, *, now: float | None = None) -> Event | None:
        now = time.monotonic() if now is None else now
        for item in list(self._pending):
            if item.visible_at > now:
                continue  # still in another delivery's visibility window
            blocked = any(
                other.event.event_id != item.event.event_id
                and other.event.grouping_key == item.event.grouping_key
                and other.visible_at > now
                for other in self._pending)
            if blocked:
                continue  # FIFO: an earlier event for this key is in flight
            self._pending.remove(item)
            item.receives += 1
            if item.receives > self.max_receives:
                self.dead_letter.append(item.event)
                continue
            item.visible_at = now + self.visibility_timeout_s
            self._pending.append(item)  # stays queued until deleted
            return item.event
        return None

    def delete(self, event: Event) -> bool:
        for item in list(self._pending):
            if item.event.event_id == event.event_id:
                self._pending.remove(item)
                return True
        return False

    def depth(self) -> int:
        return len(self._pending)

    def dlq_depth(self) -> int:
        return len(self.dead_letter)


class EventBus:
    """SNS-shaped topics fanning out to SQS-shaped queues."""

    def __init__(self) -> None:
        self._topics: dict[str, list[Queue]] = defaultdict(list)

    def subscribe(self, topic: str, queue: Queue) -> None:
        self._topics[topic].append(queue)

    def publish(self, topic: str, event: Event) -> dict[str, bool]:
        """Fan out to every subscribed queue; returns per-queue accepted."""
        return {q.name: q.enqueue(event)
                for q in self._topics.get(topic, [])}
