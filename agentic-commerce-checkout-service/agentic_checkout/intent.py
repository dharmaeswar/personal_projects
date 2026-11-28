"""Verifiable agent intent.

An AI agent that wants to spend a user's money must present a *verifiable
intent*: who it acts for, which merchant, which action, how much, and in
which currency — plus the delegation that proves the user allowed exactly
that.  Nothing here trusts the agent's word: every field is checked
against the delegation before any payment step runs.

This mirrors the concepts the Global Payments Agentic Commerce role names
(UCP / ACP / AP2 style delegated authority, verifiable intent, delegated
credentials) as deterministic, testable rules — no model calls, no network.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class AgentIntent:
    """One agent-requested commerce action."""

    agent_id: str
    user_id: str
    merchant_id: str
    action: str  # e.g. "checkout.create", "payment.authorize", "payment.capture"
    amount_cents: int
    currency: str
    idempotency_key: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Delegation:
    """What a user actually allowed an agent to do."""

    user_id: str
    agent_id: str
    allowed_actions: frozenset
    merchant_allowlist: frozenset  # empty frozenset means "any merchant"
    max_amount_cents: int
    allowed_currencies: frozenset
    expires_at: datetime


def validate_intent(intent: AgentIntent, delegation: Delegation,
                    now: datetime | None = None) -> list[str]:
    """Return a list of violations; empty means the intent is allowed."""
    now = now or datetime.now(timezone.utc)
    problems: list[str] = []
    if intent.user_id != delegation.user_id:
        problems.append("intent user does not match delegation user")
    if intent.agent_id != delegation.agent_id:
        problems.append("intent agent does not match delegation agent")
    if intent.action not in delegation.allowed_actions:
        problems.append(f"action {intent.action!r} is not in the delegation")
    if delegation.merchant_allowlist and intent.merchant_id not in delegation.merchant_allowlist:
        problems.append(f"merchant {intent.merchant_id!r} is not allowlisted")
    if intent.amount_cents <= 0:
        problems.append("amount must be positive")
    if intent.amount_cents > delegation.max_amount_cents:
        problems.append(
            f"amount {intent.amount_cents} exceeds delegated cap "
            f"{delegation.max_amount_cents}"
        )
    if intent.currency not in delegation.allowed_currencies:
        problems.append(f"currency {intent.currency!r} is not allowed")
    if now >= delegation.expires_at:
        problems.append("delegation has expired")
    if not intent.idempotency_key:
        problems.append("idempotency key is required")
    return problems


def intent_fingerprint(intent: AgentIntent) -> str:
    """Stable hash of an intent, used as audit evidence and dedup input."""
    payload = {
        "agent_id": intent.agent_id,
        "user_id": intent.user_id,
        "merchant_id": intent.merchant_id,
        "action": intent.action,
        "amount_cents": intent.amount_cents,
        "currency": intent.currency,
        "idempotency_key": intent.idempotency_key,
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()
