"""Tests: modernization adapters and their error semantics."""

import pytest

from integration_surface.adapters import build_registry
from integration_surface.context import CallerContext


def _ctx():
    return CallerContext(user_id="u1", tenant_id="tenant-demo",
                         scopes=frozenset({"amp:read", "amp:migrate"}))


def _invoke(name, args, version="1.0"):
    return build_registry().invoke(name, args, _ctx(), version)


def test_analyze_schema_counts_and_candidates():
    result = _invoke("amp.analyze_schema", {"schema": "orders"})
    assert result.ok is True
    assert result.data["tables"] == 3
    assert result.data["join_depth"] == 2
    assert "order_items" in result.data["embed_candidates"]


def test_analyze_unknown_schema_not_found():
    result = _invoke("amp.analyze_schema", {"schema": "nope"})
    assert result.error.code == "contract_violation"  # enum rejects it first


def test_transform_table_maps_types_and_strategy():
    result = _invoke("amp.transform_table",
                     {"schema": "orders", "table": "orders"}, "2.0")
    assert result.ok is True
    assert result.data["fields"]["total"] == "Decimal128"
    assert result.data["fields"]["placed_at"] == "Date"
    assert result.data["child_tables"] == ["order_items"]
    assert result.data["strategy"] in ("embed", "reference")


def test_transform_unknown_table_not_found():
    result = _invoke("amp.transform_table", {"schema": "orders", "table": "nope"})
    assert result.error.code == "not_found"


def test_transform_batch_reports_partial_success():
    result = _invoke("amp.transform_batch",
                     {"schema": "orders", "tables": ["customers", "nope", "orders"]})
    assert result.ok is False
    assert result.partial is True
    assert result.error.code == "partial_success"
    assert [r["id"] for r in result.item_results] == ["customers", "nope", "orders"]
    assert result.item_results[1]["ok"] is False


def test_dry_run_migration_mixed_outcomes():
    result = _invoke("amp.dry_run_migration", {"schema": "orders"})
    # "customers" (9 chars, odd) fails; "orders" (6) and "order_items" (11, odd) mix
    assert result.partial is True
    failed = [r["id"] for r in result.item_results if not r["ok"]]
    assert failed  # at least one table fails deterministically
    assert result.error.code == "partial_success"


def test_dry_run_full_without_downtime_rejected():
    result = _invoke("amp.dry_run_migration",
                     {"schema": "orders", "mode": "full", "allow_downtime": False})
    assert result.error.code == "contract_violation"


def test_validate_migrated_pass_and_fail():
    ok = _invoke("amp.validate_migrated",
                 {"source_rows": 1000, "migrated_rows": 1000})
    assert ok.ok is True
    assert ok.data["checks"]["row_count_match"] is True
    bad = _invoke("amp.validate_migrated",
                  {"source_rows": 1000, "migrated_rows": 997,
                   "duplicate_keys": 2, "sample_mismatches": 1})
    assert bad.ok is False
    assert bad.error.code == "validation_failed"
    assert bad.data["missing_rows"] == 3


def test_validate_negative_rows_rejected():
    result = _invoke("amp.validate_migrated",
                     {"source_rows": -1, "migrated_rows": 0})
    assert result.error.code == "contract_violation"
