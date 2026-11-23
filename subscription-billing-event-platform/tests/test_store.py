import pytest

from subscription_billing.store import (
    ConditionalWriteError, Entitlement, EntitlementStore)

NOW = 1_800_000_000
DAY = 24 * 3600


def make_ent(sub="sub-1", status="active", end=NOW + 30 * DAY):
    return Entitlement("partner-a", "cust-1", sub, "plan-monthly", status,
                       1499, period_start=NOW, period_end=end)


def test_put_and_get_roundtrip():
    store = EntitlementStore()
    store.put(make_ent())
    got = store.get("partner-a", "cust-1", "sub-1")
    assert got is not None and got.plan_id == "plan-monthly"
    assert got.price_minor == 1499 and got.version == 1


def test_put_not_exists_rejects_duplicate():
    store = EntitlementStore()
    store.put(make_ent())
    with pytest.raises(ConditionalWriteError):
        store.put(make_ent(), condition="not_exists")


def test_version_check_rejects_stale_writer():
    store = EntitlementStore()
    store.put(make_ent())
    item = make_ent()
    item.version = 1
    with pytest.raises(ConditionalWriteError):
        store.put(item, expected_version=99)


def test_version_check_accepts_matching_version_and_bumps():
    store = EntitlementStore()
    store.put(make_ent())
    item = make_ent()
    store.put(item, expected_version=1)
    assert store.get("partner-a", "cust-1", "sub-1").version == 2


def test_query_subscriber_excludes_expired():
    store = EntitlementStore()
    store.put(make_ent("sub-1", end=NOW + 30 * DAY))
    store.put(make_ent("sub-2", end=NOW - DAY))  # already expired
    rows = store.query_subscriber("partner-a", "cust-1", now=NOW)
    assert [r.subscription_id for r in rows] == ["sub-1"]


def test_count_active_counts_only_active_and_unexpired():
    store = EntitlementStore()
    store.put(make_ent("sub-1", status="active"))
    store.put(make_ent("sub-2", status="cancelled"))
    store.put(make_ent("sub-3", status="active", end=NOW - DAY))
    assert store.count_active("partner-a", now=NOW) == 1
