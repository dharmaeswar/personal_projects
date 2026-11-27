"""Privacy: consent enforcement and PII redaction.

Consent is a first-class input. A signal category the user opted out
of is excluded from batch aggregates and never served, and raw PII
fields are redacted before any signal leaves the store.
"""
from __future__ import annotations

from .models import Consent, Signal

PII_FIELDS = ("email", "free_text", "raw_prompt", "full_name")


def redact_payload(payload: dict) -> dict:
    """Drop PII fields from an event payload; keep the rest."""
    return {k: v for k, v in payload.items() if k not in PII_FIELDS}


def category_of(event_type: str) -> str:
    return {"telemetry": "telemetry", "product_usage": "usage",
            "experimentation": "experimentation"}[event_type]


def filter_by_consent(signals: list[Signal], consent: Consent) -> list[Signal]:
    """Serve-time filter: only signals in consented categories."""
    return [s for s in signals if consent.allows(s.category)]


def consented_events(events, consent: Consent):
    """Batch-time filter: drop events whose category the user opted out of."""
    return [e for e in events if consent.allows(category_of(e.event_type))]
