import pytest

from gateway import ServerRegistry


@pytest.fixture
def registry():
    return ServerRegistry(stale_after_seconds=300)


def test_register_and_get(registry):
    s = registry.register("srv-1", "prod-1", "prod", "10.0.0.1:22")
    assert registry.get("srv-1") is s
    assert s.healthy is True


def test_duplicate_registration_rejected(registry):
    registry.register("srv-1", "prod-1", "prod", "10.0.0.1:22")
    with pytest.raises(ValueError, match="already registered"):
        registry.register("srv-1", "prod-1", "prod", "10.0.0.2:22")


def test_unknown_server_returns_none(registry):
    assert registry.get("nope") is None


def test_heartbeat_marks_healthy(registry):
    registry.register("srv-1", "prod-1", "prod", "10.0.0.1:22")
    registry.mark_unhealthy("srv-1")
    registry.heartbeat("srv-1", now=5000.0)
    assert registry.get("srv-1").healthy is True
    assert registry.get("srv-1").last_heartbeat == 5000.0


def test_stale_server_goes_unhealthy(registry):
    registry.register("srv-1", "prod-1", "prod", "10.0.0.1:22")
    registry.heartbeat("srv-1", now=1000.0)
    unhealthy = registry.health_check(now=1000.0 + 301)
    assert [s.server_id for s in unhealthy] == ["srv-1"]
    assert registry.get("srv-1").healthy is False


def test_fresh_server_stays_healthy(registry):
    registry.register("srv-1", "prod-1", "prod", "10.0.0.1:22")
    registry.heartbeat("srv-1", now=1000.0)
    assert registry.health_check(now=1100.0) == []


def test_list_filters_by_environment(registry):
    registry.register("srv-1", "prod-1", "prod", "10.0.0.1:22")
    registry.register("srv-2", "stage-1", "staging", "10.0.0.2:22")
    assert [s.server_id for s in registry.list("prod")] == ["srv-1"]
    assert len(registry.list()) == 2
