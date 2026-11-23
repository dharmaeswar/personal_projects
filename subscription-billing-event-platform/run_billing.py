"""Demo: onboard partners, provision subscriptions, bill and renew.

Run:  python run_billing.py
Expected: 2 partners onboarded, 3 subscriptions provisioned, 2 charges,
1 renewal, 1 cancellation, 0 DLQ messages, p95 lookup under 1 ms.
"""

from subscription_billing import BillingService, EntitlementLookup, EntitlementStore, EventBus
from subscription_billing.billing import Partner
from subscription_billing.events import Event, Queue

NOW = 1_800_000_000  # fixed epoch for a deterministic demo


def main() -> None:
    store = EntitlementStore()
    bus = EventBus()
    billing_queue = Queue("billing-events")
    audit_queue = Queue("audit-events")
    bus.subscribe("subscription.provisioned", billing_queue)
    bus.subscribe("subscription.provisioned", audit_queue)
    svc = BillingService(store, bus)

    svc.onboard_partner(Partner("partner-prime", "Prime",
                                {"prime-monthly": 1499, "prime-annual": 14999}))
    svc.onboard_partner(Partner("partner-music", "Music",
                                {"music-monthly": 999}))
    print("partners onboarded: 2")

    subs = [
        ("partner-prime", "sub-001", "sub-001-prime-monthly", "prime-monthly"),
        ("partner-prime", "sub-002", "sub-002-prime-annual", "prime-annual"),
        ("partner-music", "sub-003", "sub-003-music-monthly", "music-monthly"),
    ]
    for partner_id, subscriber_id, subscription_id, plan_id in subs:
        result = svc.provision_subscription(Event(
            event_id=f"prov-{subscription_id}",
            event_type="subscription.provision",
            partner_id=partner_id, subscriber_id=subscriber_id,
            payload={"subscription_id": subscription_id, "plan_id": plan_id,
                     "now": NOW}))
        print(f"provision {subscription_id}: {result['status']}")
        # duplicate delivery: same dedup id must not double-provision
        again = svc.provision_subscription(Event(
            event_id=f"prov-{subscription_id}",
            event_type="subscription.provision",
            partner_id=partner_id, subscriber_id=subscriber_id,
            payload={"subscription_id": subscription_id, "plan_id": plan_id,
                     "now": NOW}))
        assert again["status"] == "provisioned", again

    print(f"fan-out: billing queue depth {billing_queue.depth()}, "
          f"audit queue depth {audit_queue.depth()}")

    charge = svc.handle_billing_event(Event(
        event_id="evt-charge-1", event_type="billing.charge",
        partner_id="partner-prime", subscriber_id="sub-001",
        payload={"subscription_id": "sub-001-prime-monthly"}))
    print(f"charge sub-001: {charge['status']} "
          f"{charge['amount_minor']} minor units")

    renew = svc.handle_billing_event(Event(
        event_id="evt-renew-1", event_type="billing.renew",
        partner_id="partner-prime", subscriber_id="sub-002",
        payload={"subscription_id": "sub-002-prime-annual"}))
    print(f"renew sub-002: {renew['status']}, "
          f"new period end {renew['period_end']}")

    cancel = svc.handle_billing_event(Event(
        event_id="evt-cancel-1", event_type="billing.cancel",
        partner_id="partner-music", subscriber_id="sub-003",
        payload={"subscription_id": "sub-003-music-monthly"}))
    print(f"cancel sub-003: {cancel['status']}")

    lookup = EntitlementLookup(store)
    for _ in range(100):
        lookup.has_active("partner-prime", "sub-001", "prime-monthly", now=NOW)
    stats = lookup.latency_stats_us()
    print(f"lookup p50 {stats['p50_us']:.1f} us, "
          f"p95 {stats['p95_us']:.1f} us over {stats['count']} lookups")
    print(f"active entitlements (partner-prime): "
          f"{store.count_active('partner-prime', now=NOW)}")
    print(f"total charged (partner-prime): "
          f"{svc.total_charged_minor('partner-prime')} minor units")
    print(f"DLQ depth: {billing_queue.dlq_depth()}")


if __name__ == "__main__":
    main()
