"""Append-only audit log. Every entry is PHI-redacted before it is stored."""

from datetime import datetime, timezone

from .phi import redact


class AuditLog:
    def __init__(self):
        self.entries = []

    def append(self, actor, action, detail=""):
        safe_detail, _ = redact(detail)
        self.entries.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "action": action,
                "detail": safe_detail,
            }
        )

    def to_list(self):
        return list(self.entries)
