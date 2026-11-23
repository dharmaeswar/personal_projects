import pytest

from subscription_billing import BillingService, EntitlementStore, EventBus
from subscription_billing.billing import Partner
from subscription_billing.events import Event, Queue

NOW = 1_800_000_000
DAY = 24 * 3600


def make_service():
    store = EntitlementStore()
    bus = EventBus()
    queue = Queue("billing-events")
    bus.subscribe("subscription.provisioned", queue)
    svc = BillingService(store, bus)
    svc.onboard_partner(Partner("partner-a", "Prime",
                                {"plan-monthly": 1499}))
    return svc, store, queue


def prov_event(sub="sub-1", plan="plan-monthly", eid="prov-1"):
    return Event(eid, "subscription.provision", "partner-a", "cust-1",
                 {"subscription_id": sub, "plan_id": plan, "now": NOW})


def bill_event(eid, kind, sub="sub-1", **extra):
    payload = {"subscription_id": sub}
    payload.update(extra)
    return Event(eid, kind, "partner-a", "cust-1", payload)


def test_onboard_rejects_duplicate_and_bad_plans():
    svc, _, _ = make_service()
    with pytest.raises(ValueError):
        svc.onboard_partner(Partner("partner-a", "Again", {"p": 100}))
    with pytest.raises(ValueError):
        svc.onboard_partner(Partner("partner-b", "NoPlans", {}))
    with pytest.raises(ValueError):
        svc.onboard_partner(Partner("partner-c", "Free", {"p": 0}))


def test_provision_creates_entitlement_and_fans_out():
    svc, store, queue = make_service()
    result = svc.provision_subscription(prov_event())
    assert result["status"] == "provisioned"
    assert result["price_minor"] == 1499
    item = store.get("partner-a", "cust-1", "sub-1")
    assert item is not None and item.status == "active"
    assert item.period_end == NOW + 30 * DAY
    assert queue.depth() == 1  # subscription.provisioned fanned out


def test_provision_is_idempotent_on_replay():
    svc, store, queue = make_service()
    first = svc.provision_subscription(prov_event())
    second = svc.provision_subscription(prov_event())
    assert first == second
    assert len(store) == 1
    assert queue.depth() == 1  # no second fan-out


def test_provision_rejects_unknown_partner_and_plan():
    svc, _, _ = make_service()
    bad_partner = Event("e1", "subscription.provision", "nope", "cust-1",
                        {"subscription_id": "s", "plan_id": "plan-monthly",
                         "now": NOW})
    assert svc.provision_subscription(bad_partner)["status"] == "failed"
    bad_plan = prov_event(plan="no-such-plan", eid="prov-2")
    assert svc.provision_subscription(bad_plan)["status"] == "failed"


def test_charge_records_and_replay_does_not_double_charge():
    svc, _, _ = make_service()
    svc.provision_subscription(prov_event())
    first = svc.handle_billing_event(bill_event("c1", "billing.charge"))
    assert first["status"] == "charged"
    assert first["amount_minor"] == 1499
    second = svc.handle_billing_event(bill_event("c1", "billing.charge"))
    assert first == second
    assert len(svc.charges) == 1
    assert svc.total_charged_minor("partner-a") == 1499


def test_renew_extends_period_and_charges_again():
    svc, store, _ = make_service()
    svc.provision_subscription(prov_event())
    before = store.get("partner-a", "cust-1", "sub-1").period_end
    result = svc.handle_billing_event(bill_event("r1", "billing.renew"))
    assert result["status"] == "renewed"
    assert result["period_end"] == before + 30 * DAY
    assert svc.charges[-1].kind == "renewal"


def test_cancel_and_dunning_update_status():
    svc, store, _ = make_service()
    svc.provision_subscription(prov_event())
    assert svc.handle_billing_event(
        bill_event("d1", "billing.dunning", attempt=2))["status"] == "past_due"
    assert store.get("partner-a", "cust-1", "sub-1").status == "past_due"
    assert svc.handle_billing_event(
        bill_event("x1", "billing.cancel"))["status"] == "cancelled"
    assert store.get("partner-a", "cust-1", "sub-1").status == "cancelled"


def test_billing_unknown_subscription_fails():
    svc, _, _ = make_service()
    result = svc.handle_billing_event(bill_event("c9", "billing.charge",
                                                sub="missing"))
    assert result["status"] == "failed"


def test_prorate_math_and_validation():
    assert BillingService.prorate(3000, 10, 30) == 1000
    assert BillingService.prorate(1499, 15, 30) == 750
    assert BillingService.prorate(1499, 0, 30) == 0
    assert BillingService.prorate(1499, 30, 30) == 1499
    with pytest.raises(ValueError):
        BillingService.prorate(100, 31, 30)
    with pytest.raises(ValueError):
        BillingService.prorate(100, 5, 0)
