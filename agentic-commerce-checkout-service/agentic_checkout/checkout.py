"""Checkout service: the deterministic backend an agent calls.

Flow for one purchase, in order — every step is checked, and a failure
stops the flow with a plain-language error instead of a partial charge:

1. `create_checkout` — intent + delegation + token + risk must all pass.
2. `authorize` — the payment credential is tokenized, risk is re-scored,
   and an authorization hold is placed.  No capture yet.
3. `capture` — settles the authorization.  Idempotent: repeating a
   capture with the same idempotency key returns the original result
   instead of charging twice.
4. `refund` — returns funds against a captured payment, capped at the
   captured amount.

All state is in-memory and all money is integer cents.  This is a demo
service: it never contacts a gateway, a bank, or a network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .audit import AuditLog
from .intent import AgentIntent, Delegation, intent_fingerprint, validate_intent
from .risk import Attempt, RiskEngine
from .tokens import DelegatedToken, ReplayGuard, TokenError, verify_token
from .vault import TokenVault


class CheckoutError(ValueError):
    """Raised when a checkout step is refused; no partial charge results."""


@dataclass
class Order:
    order_id: str
    agent_id: str
    user_id: str
    merchant_id: str
    amount_cents: int
    currency: str
    status: str  # CREATED | AUTHORIZED | CAPTURED | REFUNDED | FAILED
    payment_token: str = ""
    captured_cents: int = 0
    refunded_cents: int = 0


@dataclass
class Receipt:
    order_id: str
    action: str
    amount_cents: int
    currency: str
    status: str
    idempotency_key: str
    replayed: bool = False


class CheckoutService:
    """Wires intent, tokens, vault, risk, and audit into one service."""

    def __init__(self, *, secret: bytes, risk_engine: RiskEngine,
                 delegation: Delegation) -> None:
        self._secret = secret
        self._risk = risk_engine
        self._delegation = delegation
        self._vault = TokenVault(secret)
        self._replay = ReplayGuard()
        self.audit = AuditLog()
        self._orders: dict[str, Order] = {}
        self._captures: dict[str, Receipt] = {}
        self._counter = 0

    # -- step 1: create -------------------------------------------------
    def create_checkout(self, intent: AgentIntent, token_str: str,
                        now: datetime | None = None) -> Order:
        now = now or datetime.now(timezone.utc)
        fp = intent_fingerprint(intent)
        token = self._verified_token(token_str, now)
        problems = validate_intent(intent, self._delegation, now)
        problems += token.allows(intent.action, intent.merchant_id,
                                 intent.amount_cents, now)
        if problems:
            self._audit("checkout.rejected", fp, token.token_id, "DENY",
                        "; ".join(problems))
            raise CheckoutError("intent rejected: " + "; ".join(problems))
        decision = self._risk.score(Attempt(intent.agent_id, intent.merchant_id,
                                            intent.amount_cents, intent.currency, now))
        if decision.decision == "DENY":
            self._audit("checkout.rejected", fp, token.token_id, "DENY",
                        "; ".join(decision.reasons))
            raise CheckoutError("risk denied checkout: " + "; ".join(decision.reasons))
        self._counter += 1
        order = Order(order_id=f"ord_{self._counter:06d}",
                      agent_id=intent.agent_id, user_id=intent.user_id,
                      merchant_id=intent.merchant_id,
                      amount_cents=intent.amount_cents,
                      currency=intent.currency, status="CREATED")
        self._orders[order.order_id] = order
        self._audit("checkout.created", fp, token.token_id, decision.decision,
                    f"order {order.order_id} created")
        return order

    # -- step 2: authorize ----------------------------------------------
    def authorize(self, order_id: str, card_number: str, token_str: str,
                  idempotency_key: str,
                  now: datetime | None = None) -> Receipt:
        now = now or datetime.now(timezone.utc)
        order = self._get_order(order_id)
        token = self._verified_token(token_str, now)
        if not self._replay.check_and_mark(token.token_id, idempotency_key):
            raise CheckoutError("replayed authorization: token/key already used")
        if order.status != "CREATED":
            raise CheckoutError(f"order {order_id} is {order.status}, not CREATED")
        masked = self._vault.tokenize(card_number)
        order.payment_token = masked.token
        order.status = "AUTHORIZED"
        fp = intent_fingerprint(AgentIntent(
            order.agent_id, order.user_id, order.merchant_id,
            "payment.authorize", order.amount_cents, order.currency,
            idempotency_key))
        self._audit("payment.authorized", fp, token.token_id, "ALLOW",
                    f"order {order_id} authorized on {masked.brand} ****{masked.last4}")
        return Receipt(order_id, "authorize", order.amount_cents,
                       order.currency, "AUTHORIZED", idempotency_key)

    # -- step 3: capture (idempotent) ------------------------------------
    def capture(self, order_id: str, idempotency_key: str,
                now: datetime | None = None) -> Receipt:
        if idempotency_key in self._captures:
            prior = self._captures[idempotency_key]
            return Receipt(prior.order_id, prior.action, prior.amount_cents,
                           prior.currency, prior.status, idempotency_key,
                           replayed=True)
        order = self._get_order(order_id)
        if order.status != "AUTHORIZED":
            raise CheckoutError(f"order {order_id} is {order.status}, not AUTHORIZED")
        order.status = "CAPTURED"
        order.captured_cents = order.amount_cents
        receipt = Receipt(order_id, "capture", order.amount_cents,
                          order.currency, "CAPTURED", idempotency_key)
        self._captures[idempotency_key] = receipt
        fp = intent_fingerprint(AgentIntent(
            order.agent_id, order.user_id, order.merchant_id,
            "payment.capture", order.amount_cents, order.currency,
            idempotency_key))
        self._audit("payment.captured", fp, "", "ALLOW",
                    f"order {order_id} captured {order.amount_cents} cents")
        return receipt

    # -- step 4: refund ----------------------------------------------------
    def refund(self, order_id: str, amount_cents: int,
               idempotency_key: str) -> Receipt:
        order = self._get_order(order_id)
        if order.status not in ("CAPTURED", "REFUNDED"):
            raise CheckoutError(f"order {order_id} is {order.status}; nothing to refund")
        if amount_cents <= 0 or amount_cents > order.captured_cents - order.refunded_cents:
            raise CheckoutError("refund amount exceeds the refundable balance")
        order.refunded_cents += amount_cents
        if order.refunded_cents == order.captured_cents:
            order.status = "REFUNDED"
        return Receipt(order_id, "refund", amount_cents, order.currency,
                       order.status, idempotency_key)

    def get_order(self, order_id: str) -> Order:
        return self._get_order(order_id)

    # -- helpers -----------------------------------------------------------
    def _get_order(self, order_id: str) -> Order:
        try:
            return self._orders[order_id]
        except KeyError:
            raise CheckoutError(f"unknown order {order_id!r}") from None

    def _verified_token(self, token_str: str, now: datetime) -> DelegatedToken:
        try:
            return verify_token(token_str, self._secret, now)
        except TokenError as exc:
            raise CheckoutError(f"invalid delegated token: {exc}") from exc

    def _audit(self, event: str, fp: str, token_id: str, risk: str, outcome: str) -> None:
        self.audit.append(event=event, intent_fingerprint=fp, token_id=token_id,
                          risk_decision=risk, outcome=outcome)
