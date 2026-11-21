"""Rule-based fact extraction from claim narratives.

Each extracted fact carries a confidence score: 1.0 for a strong,
context-backed match, 0.6 for a weak or fallback match, 0.0 when the
fact is missing. A document whose mean fact confidence falls below
``REVIEW_THRESHOLD`` goes to the human-in-the-loop review queue instead
of being trusted as-is.
"""
from __future__ import annotations

import re

from .documents import BODY_PARTS, INJURIES, PROVIDERS

REVIEW_THRESHOLD = 0.8

DATE_RE = re.compile(r"\b(20\d\d)-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])\b")
AMOUNT_RE = re.compile(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
PROVIDER_RE = re.compile(
    r"(?:Treated at|treated at|Care was provided at|was treated at)\s+"
    r"([A-Z][A-Za-z ]+?(?:Hospital|Orthopedics|Care|Therapy|Clinic))")

FACTS = ("injury_type", "body_part", "incident_date", "treatment_provider",
         "claimed_amount")


def _find_injury(text: str) -> tuple[str | None, float]:
    lowered = text.lower()
    for injury in INJURIES:
        if injury in lowered:
            return injury, 1.0
    return None, 0.0


def _find_body_part(text: str) -> tuple[str | None, float]:
    lowered = text.lower()
    for part in BODY_PARTS:
        if re.search(rf"\b{part}\b", lowered):
            return part, 1.0
    return None, 0.0


def _find_date(text: str) -> tuple[str | None, float]:
    match = DATE_RE.search(text)
    if match:
        return match.group(0), 1.0
    return None, 0.0


def _find_provider(text: str) -> tuple[str | None, float]:
    match = PROVIDER_RE.search(text)
    if match:
        name = match.group(1).strip()
        if name in PROVIDERS:
            return name, 1.0
        return name, 0.6
    return None, 0.0


def _find_amount(text: str) -> tuple[float | None, float]:
    match = AMOUNT_RE.search(text)
    if match:
        return float(match.group(1).replace(",", "")), 1.0
    return None, 0.0


_EXTRACTORS = {
    "injury_type": _find_injury,
    "body_part": _find_body_part,
    "incident_date": _find_date,
    "treatment_provider": _find_provider,
    "claimed_amount": _find_amount,
}


def extract_facts(narrative: str) -> dict:
    """Extract every fact from one narrative. Returns {fact: {value, confidence}}."""
    return {
        fact: {"value": value, "confidence": confidence}
        for fact, (value, confidence) in
        ((fact, fn(narrative)) for fact, fn in _EXTRACTORS.items())
    }


def overall_confidence(facts: dict) -> float:
    """Mean confidence across all facts (0.0 when nothing was extracted)."""
    if not facts:
        return 0.0
    return sum(f["confidence"] for f in facts.values()) / len(facts)


def needs_review(facts: dict, threshold: float = REVIEW_THRESHOLD) -> bool:
    """True when the extraction is too uncertain to trust without a human.

    Any missing fact sends the document to review, as does a mean
    confidence below the threshold.
    """
    if any(detail["value"] is None for detail in facts.values()):
        return True
    return overall_confidence(facts) < threshold


def missing_facts(facts: dict) -> list[str]:
    """Names of facts that were not found at all."""
    return [fact for fact, detail in facts.items() if detail["value"] is None]
