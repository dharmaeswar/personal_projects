import pytest

from delivery_platform.agent import AgentWorkflow, AuditLog
from delivery_platform.data_interface import AgentDataInterface
from delivery_platform.services import ServiceRegistry
from delivery_platform.slo import SLOTracker
from tests.test_services import make_service


def build_interface():
    registry = ServiceRegistry()
    registry.add(make_service("checkout-api", criticality="critical"))
    registry.add(make_service("search-api", team="discovery"))
    audit_log = AuditLog()
    tracker = SLOTracker()
    for _ in range(10):
        tracker.record("checkout-api", ok=True, latency_ms=40.0)
    workflow = AgentWorkflow(audit_log)
    workflow.plan_rollout(registry.get("checkout-api"))
    return AgentDataInterface(registry, audit_log, tracker)


def test_schema_lists_four_queries():
    interface = build_interface()
    schema = interface.describe_schema()
    assert sorted(schema) == [
        "get_slo_summary", "list_audit", "list_services", "query_service",
    ]
    assert "description" in schema["query_service"]


def test_query_service_returns_compliance_slo_and_audit_count():
    interface = build_interface()
    result = interface.query_service("checkout-api")
    assert result["name"] == "checkout-api"
    assert result["compliant"] is True
    assert result["slo"]["samples"] == 10
    assert result["slo"]["availability"] == 1.0
    assert result["audit_entries"] == 1


def test_query_unknown_service_raises():
    interface = build_interface()
    with pytest.raises(ValueError, match="unknown service"):
        interface.query_service("nope")


def test_list_services_filters():
    interface = build_interface()
    assert len(interface.list_services()) == 2
    assert len(interface.list_services(team="discovery")) == 1
    assert len(interface.list_services(criticality="critical")) == 1
    assert interface.list_services(team="discovery")[0]["name"] == "search-api"


def test_get_slo_summary_validates_target():
    interface = build_interface()
    assert interface.get_slo_summary("search-api")["samples"] == 0
    with pytest.raises(ValueError, match="between 0 and 1"):
        interface.get_slo_summary("search-api", target=1.5)


def test_list_audit_filters_and_validates_limit():
    interface = build_interface()
    assert len(interface.list_audit()) == 1
    assert len(interface.list_audit(service="checkout-api")) == 1
    assert interface.list_audit(service="search-api") == []
    with pytest.raises(ValueError, match="unknown service"):
        interface.list_audit(service="nope")
    with pytest.raises(ValueError, match="must be positive"):
        interface.list_audit(limit=0)


def test_interface_exposes_no_mutation_methods():
    interface = build_interface()
    for name in ("add", "remove", "record", "execute"):
        assert not hasattr(interface, name)
