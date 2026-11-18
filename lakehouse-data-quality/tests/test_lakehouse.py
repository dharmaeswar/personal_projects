"""Tests for the lakehouse data-quality project."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.checks import (
    check_completeness,
    check_ranges,
    check_reconciliation,
    check_referential_integrity,
    check_totals,
    check_uniqueness,
    run_all_checks,
)
from lakehouse.data import (
    PLANTED_VIOLATIONS,
    generate_bronze,
    generate_orders,
)
from lakehouse.pipeline import build_gold, build_silver, read_log, write_table
from lakehouse.report import render_report
from lakehouse.schema import (
    CUSTOMERS_SCHEMA,
    GOLD_SCHEMA,
    ORDERS_SCHEMA,
    PRODUCTS_SCHEMA,
    enforce_schema,
)


@pytest.fixture(scope="module")
def bronze():
    return generate_bronze()


@pytest.fixture(scope="module")
def silver_quarantine(bronze):
    return build_silver(bronze["orders"], bronze["customers"], bronze["products"])


@pytest.fixture(scope="module")
def gold(silver_quarantine, bronze):
    silver, _ = silver_quarantine
    return build_gold(silver, bronze["products"])


def test_generate_bronze_shapes(bronze):
    assert len(bronze["orders"]) == 200
    assert len(bronze["customers"]) == 40
    assert len(bronze["products"]) == 12
    assert sum(PLANTED_VIOLATIONS.values()) == 13


def test_clean_orders_pass_schema():
    violations = enforce_schema(generate_orders(), ORDERS_SCHEMA)
    assert violations == []


def test_schema_missing_column(bronze):
    df = bronze["customers"].drop(columns=["region"])
    problems = enforce_schema(df, CUSTOMERS_SCHEMA)
    assert any("missing column: region" in p.problem for p in problems)


def test_schema_unexpected_column(bronze):
    df = bronze["products"].copy()
    df["surprise"] = 1
    problems = enforce_schema(df, PRODUCTS_SCHEMA)
    assert any("unexpected column: surprise" in p.problem for p in problems)


def test_schema_null_in_non_nullable(bronze):
    problems = enforce_schema(bronze["orders"], ORDERS_SCHEMA)
    assert any(
        "nulls in non-nullable column customer_id" in p.problem for p in problems
    )


def test_completeness_flags_null_customers(bronze):
    result = check_completeness(
        bronze["orders"], ["order_id", "customer_id", "product_id", "order_date"]
    )
    assert not result.passed
    assert "customer_id: 4 nulls" in result.detail
    assert len(result.failing_rows) == 4


def test_uniqueness_flags_duplicate_order_ids(bronze):
    result = check_uniqueness(bronze["orders"], "order_id")
    assert not result.passed
    assert len(result.failing_rows) == 3
    assert "3 duplicated order_id values" in result.detail


def test_ranges_flag_negative_quantities(bronze):
    result = check_ranges(bronze["orders"], "quantity", low=1)
    assert not result.passed
    assert len(result.failing_rows) == 2


def test_ranges_flag_future_order_date(bronze):
    result = check_ranges(
        bronze["orders"],
        "order_date",
        low=pd.Timestamp("2026-01-01"),
        high=pd.Timestamp("2026-11-30"),
    )
    assert not result.passed
    assert len(result.failing_rows) == 1


def test_fk_flags_unknown_products(bronze):
    result = check_referential_integrity(
        bronze["orders"], "product_id", bronze["products"], "product_id"
    )
    assert not result.passed
    assert len(result.failing_rows) == 2


def test_fk_ignores_null_customer_ids(bronze):
    # Null customer ids are a completeness problem, not a foreign-key problem.
    result = check_referential_integrity(
        bronze["orders"], "customer_id", bronze["customers"], "customer_id"
    )
    assert result.passed


def test_totals_flag_wrong_total(bronze):
    result = check_totals(bronze["orders"])
    assert not result.passed
    assert len(result.failing_rows) == 1


def test_bronze_check_suite_finds_six_failures(bronze):
    results = run_all_checks(
        bronze["orders"], bronze["customers"], bronze["products"]
    )
    assert len(results) == 8
    failed = [r for r in results if not r.passed]
    assert len(failed) == 6
    assert {r.name for r in failed} == {
        "completeness",
        "uniqueness:order_id",
        "range:quantity",
        "range:order_date",
        "fk:product_id->product_id",
        "totals",
    }


def test_silver_quarantine_counts(silver_quarantine):
    silver, quarantine = silver_quarantine
    assert len(silver) == 187
    assert len(quarantine) == 13
    assert len(silver) + len(quarantine) == 200


def test_quarantine_reasons_cover_every_violation_type(silver_quarantine):
    _, quarantine = silver_quarantine
    reasons = " | ".join(quarantine["quarantine_reason"])
    for label in (
        "duplicate order_id",
        "null key",
        "quantity out of range",
        "unknown product_id",
        "order_date out of range",
        "wrong total_amount",
    ):
        assert label in reasons


def test_silver_passes_every_check(silver_quarantine, bronze):
    silver, _ = silver_quarantine
    results = run_all_checks(silver, bronze["customers"], bronze["products"])
    assert all(r.passed for r in results), [str(r) for r in results]
    assert enforce_schema(silver, ORDERS_SCHEMA) == []


def test_gold_reconciles_with_silver(silver_quarantine, bronze, gold):
    silver, _ = silver_quarantine
    result = check_reconciliation(silver, bronze["products"], gold)
    assert result.passed
    assert enforce_schema(gold, GOLD_SCHEMA) == []
    assert gold["total_revenue"].sum().round(2) == silver["total_amount"].sum().round(2)


def test_delta_log_versions_increment(tmp_path):
    table_dir = tmp_path / "orders"
    first = write_table(generate_orders().head(5), table_dir, "test write")
    second = write_table(generate_orders().head(6), table_dir, "test rewrite")
    assert first["version"] == 1
    assert second["version"] == 2
    assert second["rows_added"] == 6
    assert second["rows_removed"] == 5
    assert len(read_log(table_dir)) == 2


def test_report_lists_failures_and_counts(bronze, silver_quarantine, gold):
    silver, quarantine = silver_quarantine
    results = run_all_checks(
        bronze["orders"], bronze["customers"], bronze["products"]
    )
    reconciliation = check_reconciliation(silver, bronze["products"], gold)
    report = render_report(
        results,
        bronze_rows=200,
        silver_rows=len(silver),
        quarantine_rows=len(quarantine),
        gold_groups=len(gold),
        reconciliation=reconciliation,
    )
    assert "Bronze orders: 200 rows" in report
    assert "Quarantined rows: 13 rows" in report
    assert "6 of 8 bronze checks FAILED" in report
    assert "gold matches silver." in report
