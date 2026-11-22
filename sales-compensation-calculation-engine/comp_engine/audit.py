"""Audit trail: an append-only, hash-chained event log. Every calculation,
adjustment and payment event records the hash of the previous event, so
any tampering with history breaks the chain and is detectable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AuditEvent:
    seq: int
    event: str
    entity_id: str
    detail: str
    prev_hash: str
    event_hash: str
    recorded_at: str


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: str, entity_id: str, detail: str) -> AuditEvent:
        prev_hash = self._events[-1].event_hash if self._events else "0" * 64
        recorded_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(
            {"seq": len(self._events) + 1, "event": event, "entity_id": entity_id,
             "detail": detail, "prev_hash": prev_hash, "recorded_at": recorded_at},
            sort_keys=True,
        )
        event_hash = hashlib.sha256(payload.encode()).hexdigest()
        entry = AuditEvent(
            seq=len(self._events) + 1,
            event=event,
            entity_id=entity_id,
            detail=detail,
            prev_hash=prev_hash,
            event_hash=event_hash,
            recorded_at=recorded_at,
        )
        self._events.append(entry)
        return entry

    def events(self) -> list[AuditEvent]:
        return list(self._events)

    def verify(self) -> bool:
        """Recompute the chain; False if any event was altered or removed."""
        prev_hash = "0" * 64
        for i, entry in enumerate(self._events, start=1):
            if entry.seq != i or entry.prev_hash != prev_hash:
                return False
            payload = json.dumps(
                {"seq": entry.seq, "event": entry.event, "entity_id": entry.entity_id,
                 "detail": entry.detail, "prev_hash": entry.prev_hash,
                 "recorded_at": entry.recorded_at},
                sort_keys=True,
            )
            if hashlib.sha256(payload.encode()).hexdigest() != entry.event_hash:
                return False
            prev_hash = entry.event_hash
        return True
