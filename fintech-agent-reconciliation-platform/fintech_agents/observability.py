"""Observability — CloudWatch-shaped metrics and an audit log."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field


class Metrics:
    """Counters and latency samples, the way CloudWatch would hold them."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.latencies_ms: dict[str, list[float]] = {}

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def record_latency(self, name: str, ms: float) -> None:
        self.latencies_ms.setdefault(name, []).append(ms)

    def p95_ms(self, name: str) -> float:
        samples = sorted(self.latencies_ms.get(name, []))
        if not samples:
            return 0.0
        return samples[min(len(samples) - 1, int(0.95 * len(samples)))]


@dataclass
class AuditEntry:
    seq: int
    timestamp: int
    actor: str
    action: str
    detail: dict
    prev_hash: str
    entry_hash: str = ""


class AuditLog:
    """Append-only, hash-chained audit trail (tamper-evident)."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def append(self, actor: str, action: str, detail: dict,
               *, timestamp: int | None = None) -> AuditEntry:
        prev = self.entries[-1].entry_hash if self.entries else "GENESIS"
        entry = AuditEntry(
            seq=len(self.entries) + 1,
            timestamp=int(time.time()) if timestamp is None else timestamp,
            actor=actor, action=action, detail=detail, prev_hash=prev)
        body = json.dumps([entry.seq, entry.timestamp, entry.actor,
                           entry.action, entry.detail, entry.prev_hash],
                          sort_keys=True)
        entry.entry_hash = hashlib.sha256(body.encode()).hexdigest()
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        prev = "GENESIS"
        for entry in self.entries:
            if entry.prev_hash != prev:
                return False
            body = json.dumps([entry.seq, entry.timestamp, entry.actor,
                               entry.action, entry.detail, entry.prev_hash],
                              sort_keys=True)
            if hashlib.sha256(body.encode()).hexdigest() != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True
