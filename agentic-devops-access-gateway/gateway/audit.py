"""Append-only audit log: every agent action, allowed or denied.

Each entry records who acted, what they tried, where, and the gateway's
decision with a reason. Entries are immutable once written -- there is
no delete or edit path -- so any agent session can be replayed end to
end from the log.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    timestamp: float
    actor: str
    action: str
    resource: str
    server_id: str
    decision: str  # "allowed" or "denied"
    reason: str


class AuditLog:
    def __init__(self):
        self._entries: list[AuditEntry] = []

    def record(self, actor: str, action: str, resource: str, server_id: str,
               decision: str, reason: str,
               now: float | None = None) -> AuditEntry:
        entry = AuditEntry(
            seq=len(self._entries) + 1,
            timestamp=now if now is not None else time.time(),
            actor=actor, action=action, resource=resource,
            server_id=server_id, decision=decision, reason=reason)
        self._entries.append(entry)
        return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def for_actor(self, actor: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.actor == actor]

    def denials(self) -> list[AuditEntry]:
        return [e for e in self._entries if e.decision == "denied"]

    def __len__(self) -> int:
        return len(self._entries)
