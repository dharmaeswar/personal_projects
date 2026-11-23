"""Billing service — Lambda-shaped, idempotent, retry-safe handlers.

Handlers take one event and return a result dict. Every handler is
idempotent on the event's dedup id: replaying the same event returns the
recorded outcome instead of double-charging or double-provisioning.

Flows covered:
- onboard_partner: register a billing partner with allowed plans.
- provision_subscription: create an entitlement (conditional write) and
  publish subscription.provisioned.
- handle_billing_event: charge / renew / cancel / dunning for a period.
- prorate: price for a partial period, rounded to minor units.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .events import Event, EventBus
from .store import ConditionalWriteError, Entitlement, EntitlementStore


@dataclass
class Partner:
    partner_id: str
    name: str
    plans: dict[str, int]  # plan_id -> price in minor units per period
    currency: str = "USD"


@dataclass
class ChargeRecord:
    charge_id: str
    partner_id: str
    subscriber_id: str
    subscription_id: str
    amount_minor: int
    kind: str  # charge | renewal | refund | dunning
    status: str = "succeeded"


class BillingService:
    def __init__(self, store: EntitlementStore, bus: EventBus,
                 *, period_seconds: int = 30 * 24 * 3600) -> None:
        self.store = store
        self.bus = bus
        self.period_seconds = period_seconds
        self.partners: dict[str, Partner] = {}
        self.charges: list[ChargeRecord] = []
        self._processed: dict[str, dict] = {}  # dedup_id -> result

    # -- partners ------------------------------------------------------
    def onboard_partner(self, partner: Partner) -> Partner:
        if partner.partner_id in self.partners:
            raise ValueError(f"partner already onboarded: {partner.partner_id}")
        if not partner.plans:
            raise ValueError("partner needs at least one plan")
        if any(price <= 0 for price in partner.plans.values()):
            raise ValueError("plan prices must be positive")
        self.partners[partner.partner_id] = partner
        return partner

    # -- provisioning --------------------------------------------------
    def provision_subscription(self, event: Event) -> dict:
        if event.dedup_id in self._processed:
            return self._processed[event.dedup_id]
        p = event.payload
        partner = self.partners.get(event.partner_id)
        if partner is None:
            return self._fail(event, f"unknown partner {event.partner_id}")
        plan_price = partner.plans.get(p["plan_id"])
        if plan_price is None:
            return self._fail(event, f"unknown plan {p['plan_id']}")
        now = p.get("now", int(time.time()))
        item = Entitlement(
            partner_id=event.partner_id,
            subscriber_id=event.subscriber_id,
            subscription_id=p["subscription_id"],
            plan_id=p["plan_id"],
            status="trialing" if p.get("trial_days", 0) else "active",
            price_minor=plan_price,
            currency=partner.currency,
            period_start=now,
            period_end=now + self.period_seconds,
        )
        try:
            self.store.put(item, condition="not_exists")
        except ConditionalWriteError:
            existing = self.store.get(event.partner_id,
                                      event.subscriber_id,
                                      p["subscription_id"])
            result = {"status": "already_provisioned",
                      "subscription_id": p["subscription_id"],
                      "entitlement_status": existing.status if existing else None}
            self._processed[event.dedup_id] = result
            return result
        self.bus.publish("subscription.provisioned", Event(
            event_id=f"evt-prov-{p['subscription_id']}",
            event_type="subscription.provisioned",
            partner_id=event.partner_id,
            subscriber_id=event.subscriber_id,
            payload={"subscription_id": p["subscription_id"],
                     "plan_id": p["plan_id"], "price_minor": plan_price},
            dedup_id=f"prov-{p['subscription_id']}"))
        result = {"status": "provisioned",
                  "subscription_id": p["subscription_id"],
                  "price_minor": plan_price}
        self._processed[event.dedup_id] = result
        return result

    # -- billing -------------------------------------------------------
    @staticmethod
    def prorate(price_minor: int, days_used: int, days_in_period: int) -> int:
        """Price for a partial period, rounded to the nearest minor unit."""
        if days_in_period <= 0:
            raise ValueError("days_in_period must be positive")
        if not 0 <= days_used <= days_in_period:
            raise ValueError("days_used must be within the period")
        return round(price_minor * days_used / days_in_period)

    def handle_billing_event(self, event: Event) -> dict:
        if event.dedup_id in self._processed:
            return self._processed[event.dedup_id]
        p = event.payload
        item = self.store.get(event.partner_id, event.subscriber_id,
                              p["subscription_id"])
        if item is None:
            return self._fail(event, "unknown subscription")
        kind = event.event_type
        if kind == "billing.charge":
            amount = p.get("amount_minor", item.price_minor)
            record = ChargeRecord(
                charge_id=f"ch-{event.event_id}", partner_id=event.partner_id,
                subscriber_id=event.subscriber_id,
                subscription_id=item.subscription_id,
                amount_minor=amount, kind="charge")
            self.charges.append(record)
            result = {"status": "charged", "charge_id": record.charge_id,
                      "amount_minor": amount}
        elif kind == "billing.renew":
            item.period_start = item.period_end
            item.period_end = item.period_start + self.period_seconds
            item.status = "active"
            self._bump(item)
            record = ChargeRecord(
                charge_id=f"ch-{event.event_id}", partner_id=event.partner_id,
                subscriber_id=event.subscriber_id,
                subscription_id=item.subscription_id,
                amount_minor=item.price_minor, kind="renewal")
            self.charges.append(record)
            result = {"status": "renewed", "charge_id": record.charge_id,
                      "period_end": item.period_end}
        elif kind == "billing.cancel":
            item.status = "cancelled"
            self._bump(item)
            result = {"status": "cancelled",
                      "subscription_id": item.subscription_id}
        elif kind == "billing.dunning":
            item.status = "past_due"
            self._bump(item)
            result = {"status": "past_due",
                      "subscription_id": item.subscription_id,
                      "attempt": p.get("attempt", 1)}
        else:
            return self._fail(event, f"unsupported event type {kind}")
        self._processed[event.dedup_id] = result
        return result

    def _bump(self, item: Entitlement) -> None:
        # The store holds the same object reference, so field changes are
        # already visible; the bump only advances the optimistic-lock
        # version so a concurrent writer with a stale copy is rejected.
        item.version += 1

    def _fail(self, event: Event, reason: str) -> dict:
        result = {"status": "failed", "reason": reason}
        self._processed[event.dedup_id] = result
        return result

    def total_charged_minor(self, partner_id: str) -> int:
        return sum(c.amount_minor for c in self.charges
                   if c.partner_id == partner_id and c.status == "succeeded")
