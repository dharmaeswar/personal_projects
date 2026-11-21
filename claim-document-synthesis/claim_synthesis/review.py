"""Human-in-the-loop review queue and audit log.

Low-confidence extractions wait in the queue until a reviewer acts:
``approve`` accepts the facts as extracted, ``correct`` replaces fact
values with reviewer-supplied ones, ``reject`` marks the document
invalid with a reason. Every decision is appended to the audit log with
actor and timestamp, so any claim can be replayed end to end.
"""
from __future__ import annotations

from datetime import datetime, timezone

ACTIONS = ("approve", "correct", "reject")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewQueue:
    """In-memory review queue plus append-only audit log."""

    def __init__(self) -> None:
        self.queued: dict[str, dict] = {}
        self.audit_log: list[dict] = []

    def enqueue(self, claim_id: str, tenant_id: str, facts: dict,
                confidence: float) -> None:
        self.queued[claim_id] = {
            "claim_id": claim_id,
            "tenant_id": tenant_id,
            "facts": facts,
            "confidence": confidence,
            "status": "pending",
            "queued_at": utc_now(),
        }

    def decide(self, claim_id: str, tenant_id: str, action: str, actor: str,
               corrections: dict | None = None, reason: str = "") -> dict:
        """Apply a review decision. Raises KeyError / ValueError on misuse."""
        if action not in ACTIONS:
            raise ValueError(f"Unknown review action: {action!r}. Choose from {ACTIONS}")
        item = self.queued.get(claim_id)
        if item is None:
            raise KeyError(f"Claim {claim_id} is not in the review queue")
        if item["tenant_id"] != tenant_id:
            raise PermissionError(
                f"Claim {claim_id} belongs to tenant {item['tenant_id']}, "
                f"not {tenant_id}")
        if item["status"] != "pending":
            raise ValueError(f"Claim {claim_id} was already {item['status']}")
        if action == "correct":
            if not corrections:
                raise ValueError("A 'correct' decision needs corrected fact values")
            for fact, value in corrections.items():
                if fact not in item["facts"]:
                    raise ValueError(f"Unknown fact: {fact!r}")
                item["facts"][fact] = {"value": value, "confidence": 1.0,
                                       "corrected_by": actor}
        item["status"] = {"approve": "approved", "correct": "corrected",
                          "reject": "rejected"}[action]
        item["decided_by"] = actor
        item["decided_at"] = utc_now()
        if reason:
            item["reason"] = reason
        self.audit_log.append({
            "claim_id": claim_id, "tenant_id": tenant_id, "action": action,
            "actor": actor, "reason": reason,
            "corrected_facts": sorted(corrections) if corrections else [],
            "at": utc_now(),
        })
        return item

    def pending_for_tenant(self, tenant_id: str) -> list[dict]:
        return [item for item in self.queued.values()
                if item["tenant_id"] == tenant_id and item["status"] == "pending"]
