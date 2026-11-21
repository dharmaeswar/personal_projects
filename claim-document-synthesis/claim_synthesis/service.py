"""Service layer: ingest -> extract -> synthesize -> review queue.

One call to :func:`ingest_claim` runs the whole pipeline for a document:
facts are extracted, a summary is synthesised, and the claim is either
trusted (high confidence) or queued for human review (low confidence).
Review decisions go through the same service so the audit log stays
complete.
"""
from __future__ import annotations

from .documents import TENANTS
from .extraction import extract_facts, needs_review, overall_confidence
from .review import ReviewQueue
from .store import ClaimStore
from .synthesis import synthesize_summary


class ClaimSynthesisService:
    """Orchestrates the claim pipeline over a store and a review queue."""

    def __init__(self, store: ClaimStore | None = None,
                 queue: ReviewQueue | None = None) -> None:
        self.store = store or ClaimStore()
        self.queue = queue or ReviewQueue()

    def ingest_claim(self, document: dict) -> dict:
        """Process one claim document end to end. Returns the stored claim."""
        tenant_id = document["tenant_id"]
        if tenant_id not in TENANTS:
            raise ValueError(f"Unknown tenant: {tenant_id!r}")
        for field in ("claim_id", "claimant_name", "narrative"):
            if not document.get(field):
                raise ValueError(f"Document is missing required field: {field}")
        facts = extract_facts(document["narrative"])
        confidence = overall_confidence(facts)
        summary = synthesize_summary(document["claim_id"],
                                     document["claimant_name"], facts)
        claim = {
            "claim_id": document["claim_id"],
            "tenant_id": tenant_id,
            "claimant_name": document["claimant_name"],
            "submitted_date": document.get("submitted_date", ""),
            "narrative": document["narrative"],
            "facts": facts,
            "confidence": confidence,
            "summary": summary,
            "status": "queued_for_review" if needs_review(facts) else "trusted",
        }
        self.store.put(claim)
        if needs_review(facts):
            self.queue.enqueue(document["claim_id"], tenant_id, facts, confidence)
        return claim

    def review_claim(self, claim_id: str, tenant_id: str, action: str,
                     actor: str, corrections: dict | None = None,
                     reason: str = "") -> dict:
        """Apply a review decision and update the stored claim to match."""
        item = self.queue.decide(claim_id, tenant_id, action, actor,
                                 corrections, reason)
        claim = self.store.get(claim_id, tenant_id)
        if action in ("approve", "correct"):
            claim["facts"] = item["facts"]
            claim["summary"] = synthesize_summary(
                claim_id, claim["claimant_name"], item["facts"])
            claim["confidence"] = overall_confidence(item["facts"])
            claim["status"] = "trusted"
        else:
            claim["status"] = "rejected"
        return claim

    def get_claim(self, claim_id: str, tenant_id: str) -> dict:
        return self.store.get(claim_id, tenant_id)

    def list_claims(self, tenant_id: str) -> list[dict]:
        if tenant_id not in TENANTS:
            raise ValueError(f"Unknown tenant: {tenant_id!r}")
        return self.store.list_for_tenant(tenant_id)

    def review_queue(self, tenant_id: str) -> list[dict]:
        if tenant_id not in TENANTS:
            raise ValueError(f"Unknown tenant: {tenant_id!r}")
        return self.queue.pending_for_tenant(tenant_id)
