"""Claim synthesis: turn extracted facts into a reviewer-ready summary.

The synthesiser is deterministic and template-based: it states exactly
which facts it used, flags anything missing or low-confidence, and never
invents a value. In production this is the seam where an LLM call would
plug in; the summary records its source (``template``) so a reviewer can
tell machine-drafted text from human-confirmed facts.
"""
from __future__ import annotations

from .extraction import missing_facts


def synthesize_summary(claim_id: str, claimant_name: str, facts: dict) -> dict:
    """Build a summary dict from extracted facts. Never invents values."""
    injury = facts["injury_type"]["value"]
    body_part = facts["body_part"]["value"]
    incident_date = facts["incident_date"]["value"]
    provider = facts["treatment_provider"]["value"]
    amount = facts["claimed_amount"]["value"]

    if injury and body_part:
        headline = f"{claimant_name} claims a {injury} to the {body_part}."
    elif injury:
        headline = f"{claimant_name} claims a {injury} (body part not stated)."
    else:
        headline = f"{claimant_name} filed a claim (injury type not stated)."

    details: list[str] = []
    if incident_date:
        details.append(f"Incident date: {incident_date}.")
    if provider:
        details.append(f"Treated at {provider}.")
    if amount is not None:
        details.append(f"Amount claimed: ${amount:,.2f}.")
    if not details:
        details.append("No supporting details extracted from the narrative.")

    missing = missing_facts(facts)
    flags = [f"missing {fact}" for fact in missing]
    low_confidence = [fact for fact, detail in facts.items()
                      if detail["value"] is not None and detail["confidence"] < 1.0]
    flags += [f"low-confidence {fact}" for fact in low_confidence]

    return {
        "claim_id": claim_id,
        "headline": headline,
        "details": " ".join(details),
        "flags": flags,
        "source": "template",
    }
