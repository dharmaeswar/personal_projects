"""Audit log: a hash-chained, append-only record of every agent action.

Each entry records the intent fingerprint, the token id, the risk
decision, and the outcome — the transaction evidence an agentic commerce
platform needs for disputes and reporting.  Entries are hash-chained:
each entry stores the hash of the previous one, so `verify_chain`
detects any entry that was edited, deleted, or reordered after the fact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    at: str
    event: str
    intent_fingerprint: str
    token_id: str
    risk_decision: str
    outcome: str
    prev_hash: str
    entry_hash: str


def _entry_hash(seq: int, at: str, event: str, intent_fingerprint: str,
                token_id: str, risk_decision: str, outcome: str,
                prev_hash: str) -> str:
    raw = json.dumps(
        [seq, at, event, intent_fingerprint, token_id, risk_decision,
         outcome, prev_hash],
        sort_keys=True,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class AuditLog:
    """Append-only log; entries are immutable once written."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, *, event: str, intent_fingerprint: str, token_id: str,
               risk_decision: str, outcome: str) -> AuditEntry:
        prev = self._entries[-1].entry_hash if self._entries else "GENESIS"
        at = datetime.now(timezone.utc).isoformat()
        seq = len(self._entries) + 1
        entry_hash = _entry_hash(seq, at, event, intent_fingerprint, token_id,
                                risk_decision, outcome, prev)
        entry = AuditEntry(seq, at, event, intent_fingerprint, token_id,
                           risk_decision, outcome, prev, entry_hash)
        self._entries.append(entry)
        return entry

    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def verify_chain(self) -> bool:
        """True only if every entry's hash and linkage are intact."""
        prev = "GENESIS"
        for entry in self._entries:
            if entry.prev_hash != prev:
                return False
            expected = _entry_hash(
                entry.seq, entry.at, entry.event, entry.intent_fingerprint,
                entry.token_id, entry.risk_decision, entry.outcome,
                entry.prev_hash,
            )
            if expected != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True
