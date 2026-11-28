"""Wiring and demo: build a service, then run one agent purchase end to end.

The demo uses synthetic data only — a fake agent, a fake user, a fake
merchant, and a test card number.  It shows the full flow an AI agent
would take through the platform: delegated token, verifiable intent,
checkout, authorization with tokenization, idempotent capture, and the
audit trail that records every step.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .checkout import CheckoutService
from .intent import AgentIntent, Delegation
from .risk import RiskEngine
from .tokens import issue_token

DEMO_SECRET = b"demo-only-secret-do-not-use-in-production"
TEST_CARD = "4242424242424242"  # standard test card number, not a real card


def build_service(*, merchant_median_cents: dict | None = None) -> CheckoutService:
    """Build a service with a demo delegation for one agent and one user."""
    now = datetime.now(timezone.utc)
    delegation = Delegation(
        user_id="user_001",
        agent_id="agent_shopper_01",
        allowed_actions=frozenset(
            {"checkout.create", "payment.authorize", "payment.capture",
             "payment.refund"}
        ),
        merchant_allowlist=frozenset({"merchant_books", "merchant_groceries"}),
        max_amount_cents=200_00,  # $200 cap per purchase
        allowed_currencies=frozenset({"USD"}),
        expires_at=now + timedelta(days=30),
    )
    risk = RiskEngine(
        merchant_median_cents=merchant_median_cents
        or {"merchant_books": 2500, "merchant_groceries": 8000},
    )
    return CheckoutService(secret=DEMO_SECRET, risk_engine=risk,
                           delegation=delegation)


def demo() -> None:
    now = datetime.now(timezone.utc)
    service = build_service()
    token = issue_token(
        agent_id="agent_shopper_01", user_id="user_001",
        scopes=["checkout.create", "payment.authorize", "payment.capture"],
        merchant_allowlist=["merchant_books"],
        max_amount_cents=200_00,
        expires_at=now + timedelta(hours=1),
        secret=DEMO_SECRET,
    )
    intent = AgentIntent(
        agent_id="agent_shopper_01", user_id="user_001",
        merchant_id="merchant_books", action="checkout.create",
        amount_cents=4999, currency="USD", idempotency_key="demo-key-001",
    )
    order = service.create_checkout(intent, token, now)
    print(f"checkout created: {order.order_id} ${order.amount_cents / 100:.2f} "
          f"at {order.merchant_id} (status {order.status})")
    receipt = service.authorize(order.order_id, TEST_CARD, token,
                                "demo-key-002", now)
    print(f"authorized: {receipt.status} on tokenized card")
    receipt = service.capture(order.order_id, "demo-key-003", now)
    print(f"captured: {receipt.status} ${receipt.amount_cents / 100:.2f}")
    again = service.capture(order.order_id, "demo-key-003", now)
    print(f"repeat capture with same key: replayed={again.replayed}, "
          f"no double charge")
    print(f"audit chain valid: {service.audit.verify_chain()} "
          f"({len(service.audit.entries())} entries)")
