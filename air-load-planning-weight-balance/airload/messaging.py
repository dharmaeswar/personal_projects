"""Event-driven messaging: an in-memory SNS/SQS-style bus.

A Topic fans events out to subscribed Queues. A Queue delivers a message
a bounded number of times; after `max_receives` failed deliveries the
message moves to the dead-letter queue — the same shape as the SNS/SQS
flow the SABLE portfolio uses to move load plans between systems.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field


@dataclass
class Message:
    message_id: str
    body: dict
    receives: int = 0


@dataclass
class Queue:
    name: str
    max_receives: int = 3
    _pending: list[Message] = field(default_factory=list)
    _inflight: dict[str, Message] = field(default_factory=dict)
    dead_letter: list[Message] = field(default_factory=list)

    def enqueue(self, body: dict) -> Message:
        msg = Message(message_id=str(uuid.uuid4()), body=body)
        self._pending.append(msg)
        return msg

    def receive(self) -> Message | None:
        if not self._pending:
            return None
        msg = self._pending.pop(0)
        msg.receives += 1
        self._inflight[msg.message_id] = msg
        return msg

    def acknowledge(self, message_id: str) -> None:
        self._inflight.pop(message_id, None)

    def fail(self, message_id: str) -> None:
        """Return a failed message for redelivery, or dead-letter it."""
        msg = self._inflight.pop(message_id, None)
        if msg is None:
            raise KeyError(f"message {message_id} is not in flight")
        if msg.receives >= self.max_receives:
            self.dead_letter.append(msg)
        else:
            self._pending.append(msg)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def dead_letter_count(self) -> int:
        return len(self.dead_letter)


class Topic:
    """Fan-out topic: every published event reaches each subscribed queue."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.subscriptions: list[Queue] = []

    def subscribe(self, queue: Queue) -> None:
        if queue not in self.subscriptions:
            self.subscriptions.append(queue)

    def publish(self, event_type: str, payload: dict) -> list[Message]:
        body = {"event_type": event_type, "payload": payload}
        return [q.enqueue(body) for q in self.subscriptions]


def encode_event(body: dict) -> str:
    return json.dumps(body, sort_keys=True)


def decode_event(raw: str) -> dict:
    return json.loads(raw)
