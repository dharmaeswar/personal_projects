import pytest

from delivery_platform.services import Service, ServiceRegistry


def make_service(name="checkout-api", **overrides):
    base = dict(
        name=name, team="payments", owner="dharma", backup_owner="priya",
        language="Java", repo="payments/checkout-api",
        rollback_version="v1.42.0",
        rollback_steps=["shift traffic back", "verify error rate"],
    )
    base.update(overrides)
    return Service(**base)


def test_add_and_get():
    registry = ServiceRegistry()
    service = make_service()
    registry.add(service)
    assert len(registry) == 1
    assert registry.get("checkout-api") is service
    assert registry.get("missing") is None


def test_duplicate_add_raises():
    registry = ServiceRegistry()
    registry.add(make_service())
    with pytest.raises(ValueError, match="already registered"):
        registry.add(make_service())


def test_empty_name_raises():
    registry = ServiceRegistry()
    with pytest.raises(ValueError, match="must not be empty"):
        registry.add(make_service(name=""))


def test_bad_criticality_raises():
    registry = ServiceRegistry()
    with pytest.raises(ValueError, match="unknown criticality"):
        registry.add(make_service(criticality="urgent"))


def test_list_filters_by_team_and_criticality():
    registry = ServiceRegistry()
    registry.add(make_service("a", team="payments", criticality="critical"))
    registry.add(make_service("b", team="payments"))
    registry.add(make_service("c", team="discovery"))
    assert [s.name for s in registry.list(team="payments")] == ["a", "b"]
    assert [s.name for s in registry.list(criticality="critical")] == ["a"]
    assert [s.name for s in registry.list()] == ["a", "b", "c"]


def test_remove_and_unknown_remove_raises():
    registry = ServiceRegistry()
    registry.add(make_service())
    registry.remove("checkout-api")
    assert len(registry) == 0
    with pytest.raises(ValueError, match="unknown service"):
        registry.remove("checkout-api")


def test_to_dict_from_dict_roundtrip():
    service = make_service()
    restored = Service.from_dict(service.to_dict())
    assert restored == service
    assert restored.canary_stages == [5, 25, 50, 100]
