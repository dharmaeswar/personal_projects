"""Observability: per-action metrics and a hash-chained audit log.

Metrics are counters plus simulated-latency samples (ops charged at a
fixed 1 ms each — deterministic in this local model). The audit log is
append-only: each entry carries the SHA-256 of the previous entry, so a
tampered or deleted entry breaks the chain and is detectable.
"""

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class ActionMetrics:
    invocations: int = 0
    errors: int = 0
    denials: int = 0
    timeouts: int = 0
    latencies_ms: list = field(default_factory=list)

    def record(self, simulated_ms: int, error: bool, denied: bool, timed_out: bool) -> None:
        self.invocations += 1
        self.latencies_ms.append(simulated_ms)
        if error:
            self.errors += 1
        if denied:
            self.denials += 1
        if timed_out:
            self.timeouts += 1

    def p95_ms(self) -> int:
        if not self.latencies_ms:
            return 0
        ordered = sorted(self.latencies_ms)
        return ordered[max(0, int(len(ordered) * 0.95) - 1)]


@dataclass
class AuditEntry:
    seq: int
    tenant_id: str
    action_id: str
    trigger: str
    outcome: str
    detail: str
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        payload = json.dumps(
            [self.seq, self.tenant_id, self.action_id, self.trigger,
             self.outcome, self.detail, self.prev_hash],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class AuditLog:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def append(self, tenant_id: str, action_id: str, trigger: str,
               outcome: str, detail: str) -> AuditEntry:
        prev = self.entries[-1].entry_hash if self.entries else "GENESIS"
        entry = AuditEntry(
            seq=len(self.entries) + 1,
            tenant_id=tenant_id,
            action_id=action_id,
            trigger=trigger,
            outcome=outcome,
            detail=detail,
            prev_hash=prev,
        )
        entry.entry_hash = entry.compute_hash()
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        prev = "GENESIS"
        for entry in self.entries:
            if entry.prev_hash != prev:
                return False
            if entry.compute_hash() != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True
