"""Tests: registry dispatch, versioning, auth, observability wiring."""

import pytest

from integration_surface.adapters import ModelStub, build_registry
from integration_surface.context import CallerContext


def _ctx(scopes=("amp:read", "amp:migrate")):
    return CallerContext(user_id="u1", tenant_id="tenant-demo",
                         scopes=frozenset(scopes))


def test_list_tools_exposes_definitions():
    tools = build_registry().list_tools()
    names = {t["name"] for t in tools}
    assert "amp.analyze_schema" in names
    assert "amp.transform_table" in names
    assert "amp.suggest_mapping" in names
    assert all("inputSchema" in t for t in tools)


def test_invoke_valid_call_succeeds_and_is_observed():
    registry = build_registry()
    result = registry.invoke("amp.analyze_schema", {"schema": "orders"}, _ctx())
    assert result.ok is True
    assert result.data["tables"] == 3
    assert result.data["columns"] == 14
    assert registry.observer.metrics.summary("amp.analyze_schema")["calls"] == 1
    assert len(registry.observer.traces) == 1
    assert registry.observer.traces[0].status == "ok"


def test_malformed_call_fails_fast_with_contract_error():
    registry = build_registry()
    result = registry.invoke("amp.analyze_schema", {}, _ctx())
    assert result.ok is False
    assert result.error.code == "contract_violation"


def test_unknown_tool_reports_not_found():
    registry = build_registry()
    result = registry.invoke("amp.nope", {}, _ctx())
    assert result.error.code == "tool_not_found"


def test_missing_scope_is_forbidden_not_internal():
    registry = build_registry()
    result = registry.invoke(
        "amp.dry_run_migration", {"schema": "orders"}, _ctx(scopes=("amp:read",)))
    assert result.ok is False
    assert result.error.code == "forbidden"


def test_versioning_v1_still_works_after_v2():
    registry = build_registry()
    v1 = registry.invoke("amp.transform_table",
                         {"schema": "orders", "table": "customers"}, _ctx(), "1.0")
    v2 = registry.invoke("amp.transform_table",
                         {"schema": "orders", "table": "customers",
                          "strategy": "embed"}, _ctx(), "2.0")
    assert v1.ok is True and v2.ok is True
    assert v2.data["strategy"] == "embed"


def test_cross_tenant_call_is_denied():
    registry = build_registry()
    result = registry.invoke(
        "amp.analyze_schema", {"schema": "orders", "tenant": "tenant-other"}, _ctx())
    assert result.ok is False
    assert result.error.code == "forbidden"


def test_nondeterministic_model_retries_then_succeeds():
    model = ModelStub(seed=3, fail_times=2)
    registry = build_registry(model)
    result = registry.invoke(
        "amp.suggest_mapping",
        {"prompt": "map orders", "seed": 3, "max_retries": 2}, _ctx())
    assert result.ok is True
    assert result.data["attempts"] == 3
    assert model.calls == 3


def test_model_failure_after_retries_is_retryable_error():
    model = ModelStub(seed=3, fail_times=10)
    registry = build_registry(model)
    result = registry.invoke(
        "amp.suggest_mapping",
        {"prompt": "map orders", "seed": 3, "max_retries": 1}, _ctx())
    assert result.ok is False
    assert result.error.code == "model_unavailable"
    assert result.error.details["attempts"] == 2


def test_same_seed_same_suggestion():
    a = ModelStub(seed=7).suggest("map orders")
    b = ModelStub(seed=7).suggest("map orders")
    c = ModelStub(seed=8).suggest("map orders")
    assert a == b
    assert a in ("embed child rows as an array in the parent document",
                 "keep a reference and denormalize the display fields",
                 "split into two collections with a lookup at read time")
    assert isinstance(c, str)


def test_handler_exception_becomes_internal_error_not_crash():
    from integration_surface.tools import Tool
    registry = build_registry()

    def boom(ctx, args):
        raise RuntimeError("kaboom")

    registry.register(Tool(name="amp.boom", version="1.0", description="boom",
                           input_schema={"type": "object", "properties": {}},
                           handler=boom))
    result = registry.invoke("amp.boom", {}, _ctx())
    assert result.ok is False
    assert result.error.code == "internal_error"
