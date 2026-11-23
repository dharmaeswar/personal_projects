from subscription_billing import (
    BillingService, EntitlementLookup, EntitlementStore, EventBus)
from subscription_billing.billing import Partner
from subscription_billing.events import Event

NOW = 1_800_000_000
DAY = 24 * 3600


def make_lookup():
    store = EntitlementStore()
    svc = BillingService(store, EventBus())
    svc.onboard_partner(Partner("partner-a", "Prime",
                                {"plan-monthly": 1499, "plan-annual": 14999}))
    svc.provision_subscription(Event(
        "prov-1", "subscription.provision", "partner-a", "cust-1",
        {"subscription_id": "sub-1", "plan_id": "plan-monthly", "now": NOW}))
    return svc, store, EntitlementLookup(store)


def test_active_entitlement_found():
    _, _, lookup = make_lookup()
    assert lookup.has_active("partner-a", "cust-1", "plan-monthly",
                             now=NOW) is True


def test_wrong_plan_or_subscriber_not_found():
    _, _, lookup = make_lookup()
    assert lookup.has_active("partner-a", "cust-1", "plan-annual",
                             now=NOW) is False
    assert lookup.has_active("partner-a", "cust-2", "plan-monthly",
                             now=NOW) is False
    assert lookup.has_active("partner-b", "cust-1", "plan-monthly",
                             now=NOW) is False


def test_expired_entitlement_not_active():
    _, _, lookup = make_lookup()
    assert lookup.has_active("partner-a", "cust-1", "plan-monthly",
                             now=NOW + 40 * DAY) is False


def test_cancelled_entitlement_not_active_after_rebuild():
    svc, _, lookup = make_lookup()
    svc.handle_billing_event(Event(
        "x1", "billing.cancel", "partner-a", "cust-1",
        {"subscription_id": "sub-1"}))
    lookup.rebuild()
    assert lookup.has_active("partner-a", "cust-1", "plan-monthly",
                             now=NOW) is False


def test_latency_stats_reported():
    _, _, lookup = make_lookup()
    for _ in range(10):
        lookup.has_active("partner-a", "cust-1", "plan-monthly", now=NOW)
    stats = lookup.latency_stats_us()
    assert stats["count"] == 10
    assert stats["p50_us"] >= 0
    assert stats["p95_us"] >= stats["p50_us"]
    assert stats["max_us"] >= stats["p95_us"]
