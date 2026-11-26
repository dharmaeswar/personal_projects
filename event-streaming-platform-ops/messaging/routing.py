"""Event routing: EventBridge-style rules, SNS fanout, SQS queues,
a dead-letter queue, and a RabbitMQ-style topic exchange.

Local simulation only: no real AWS or RabbitMQ service is called.
Events are plain dicts; routing decisions are pure functions so the
behaviour is testable without any broker.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def match_pattern(event: dict, pattern: dict) -> bool:
    """EventBridge-style matching: every pattern key must match.

    A pattern value is a list of allowed values; a nested dict recurses.
    An event field missing from the event does not match.
    """
    for key, allowed in pattern.items():
        if key not in event:
            return False
        value = event[key]
        if isinstance(allowed, dict):
            if not isinstance(value, dict):
                return False
            if not match_pattern(value, allowed):
                return False
        else:
            allowed_values = allowed if isinstance(allowed, list) else [allowed]
            if value not in allowed_values:
                return False
    return True


@dataclass
class Rule:
    name: str
    pattern: dict
    targets: list[str]  # queue names that receive matching events

    def matches(self, event: dict) -> bool:
        return match_pattern(event, self.pattern)


@dataclass
class Queue:
    name: str
    messages: list[dict] = field(default_factory=list)
    receive_counts: dict[int, int] = field(default_factory=dict)
    max_receives: int = 3
    dead_letter: "Queue | None" = None

    def send(self, message: dict) -> int:
        self.messages.append(message)
        return len(self.messages) - 1

    def receive(self, max_messages: int = 1) -> list[dict]:
        taken = self.messages[:max_messages]
        for i, _msg in enumerate(taken):
            self.receive_counts[i] = self.receive_counts.get(i, 0) + 1
        return taken

    def acknowledge(self, index: int) -> None:
        if 0 <= index < len(self.messages):
            del self.messages[index]
            self.receive_counts.pop(index, None)

    def redrive(self) -> int:
        """Move messages that exceeded max receives to the DLQ.

        Returns the number of messages moved.
        """
        if self.dead_letter is None:
            return 0
        moved = 0
        kept: list[dict] = []
        kept_counts: dict[int, int] = {}
        for i, msg in enumerate(self.messages):
            if self.receive_counts.get(i, 0) >= self.max_receives:
                self.dead_letter.send(msg)
                moved += 1
            else:
                kept_counts[len(kept)] = self.receive_counts.get(i, 0)
                kept.append(msg)
        self.messages = kept
        self.receive_counts = kept_counts
        return moved


def topic_exchange_match(routing_key: str, binding_key: str) -> bool:
    """RabbitMQ topic-exchange matching: ``*`` matches one word,
    ``#`` matches zero or more words, words split on ``.``."""
    rk = routing_key.split(".")
    bk = binding_key.split(".")

    def rec(r: list[str], b: list[str]) -> bool:
        if not b:
            return not r
        if b[0] == "#":
            return any(rec(r[i:], b[1:]) for i in range(len(r) + 1))
        if not r:
            return False
        if b[0] == "*":
            return rec(r[1:], b[1:])
        return b[0] == r[0] and rec(r[1:], b[1:])

    return rec(rk, bk)


class EventBus:
    """Routes events through rules to queues (EventBridge + SNS fanout)."""

    def __init__(self):
        self.rules: list[Rule] = []
        self.queues: dict[str, Queue] = {}

    def add_queue(self, queue: Queue) -> None:
        self.queues[queue.name] = queue

    def add_rule(self, rule: Rule) -> None:
        for target in rule.targets:
            if target not in self.queues:
                raise ValueError(f"rule {rule.name!r} targets unknown "
                                 f"queue {target!r}")
        self.rules.append(rule)

    def publish(self, event: dict) -> dict[str, int]:
        """Deliver the event to every queue matched by at least one rule.

        Returns queue name -> number of deliveries (fanout count).
        """
        delivered: dict[str, int] = {}
        for rule in self.rules:
            if rule.matches(event):
                for target in rule.targets:
                    self.queues[target].send(event)
                    delivered[target] = delivered.get(target, 0) + 1
        return delivered
