"""Tests for the talent data-foundations module (lakehouse/talent.py)."""

from __future__ import annotations

import pandas as pd
import pytest

from lakehouse.talent import (
    build_analytics_view,
    build_operational_view,
    build_unified_model,
    check_unified_reconciliation,
    generate_talent,
    generate_talent_events,
    load_learning_batch,
    quarantine_employees,
    quarantine_learning,
    run_talent_stream,
    tune_query_demo,
    validate_employees,
    validate_learning,
)


@pytest.fixture(scope="module")
def data():
    return generate_talent()


def test_domain_shapes(data):
    assert len(data["roles"]) == 20
    assert data["roles"]["role_id"].is_unique
    assert len(data["skills"]) == 30
    assert data["skills"]["skill_id"].is_unique
    assert len(data["employees"]) == 60
    assert len(data["employee_skills"]) >= 120  # 2-5 skills per employee
    # 180 base learning rows + 2 planted duplicate deliveries.
    assert len(data["learning"]) == 182


def test_learning_checks_fail_as_designed(data):
    results = validate_learning(data["learning"], data["employees"], data["skills"])
    by_name = {r.name: r for r in results}
    assert by_name["completeness"].passed is False  # 2 null employee_ids
    assert by_name["uniqueness:record_id"].passed is False  # 2 duplicate record_ids
    assert by_name["range:score"].passed is True
    assert by_name["fk:employee_id->employee_id"].passed is False  # EMP-9999
    assert by_name["fk:skill_id->skill_id"].passed is False  # S-999
    assert by_name["learning_after_hire"].passed is False  # 1 before hire
    # Each violation type owns exactly the rows it planted.
    assert len(by_name["completeness"].failing_rows) == 2
    assert len(by_name["uniqueness:record_id"].failing_rows) == 2
    assert len(by_name["fk:employee_id->employee_id"].failing_rows) == 1
    assert len(by_name["fk:skill_id->skill_id"].failing_rows) == 1
    assert len(by_name["learning_after_hire"].failing_rows) == 1


def test_employee_checks_fail_as_designed(data):
    results = validate_employees(data["employees"], data["roles"])
    by_name = {r.name: r for r in results}
    assert by_name["completeness"].passed is True
    assert by_name["uniqueness:employee_id"].passed is True
    assert by_name["fk:role_id->role_id"].passed is False  # R-999
    assert len(by_name["fk:role_id->role_id"].failing_rows) == 1


def test_quarantine_counts(data):
    silver_learning, quar_learning = quarantine_learning(
        data["learning"], data["employees"], data["skills"]
    )
    # 7 bad learning rows quarantined, each with a named reason.
    assert len(quar_learning) == 7
    assert len(silver_learning) == 175
    assert silver_learning["record_id"].is_unique
    assert "quarantine_reason" in quar_learning.columns
    assert quar_learning["quarantine_reason"].str.len().gt(0).all()
    silver_employees, quar_employees = quarantine_employees(
        data["employees"], data["roles"]
    )
    assert len(quar_employees) == 1
    assert len(silver_employees) == 59
    assert quar_employees.iloc[0]["role_id"] == "R-999"


def test_unified_model(data):
    silver_learning, _ = quarantine_learning(
        data["learning"], data["employees"], data["skills"]
    )
    silver_employees, _ = quarantine_employees(data["employees"], data["roles"])
    unified = build_unified_model(
        silver_employees,
        data["roles"],
        data["employee_skills"],
        data["skills"],
        silver_learning,
    )
    assert len(unified) == 59
    assert unified["employee_id"].is_unique
    # Every unified row has a real role and department.
    assert unified["role_title"].notna().all()
    assert unified["department"].notna().all()
    assert unified["department"].isin(
        ["Engineering", "Data", "People Ops", "Finance", "Product"]
    ).all()
    # Skill counts come from the bridge table.
    assert unified["skill_count"].between(2, 5).all()
    # Learning counts sum back to silver learning rows for silver employees
    # (2 silver learning rows belong to the quarantined employee and are held back).
    vendable = silver_learning[
        silver_learning["employee_id"].isin(set(silver_employees["employee_id"]))
    ]
    assert int(unified["learning_count"].sum()) == len(vendable)
    # No learning predates hire in the unified model (hire_date rides along).
    assert (
        unified["last_learning_date"].isna()
        | (unified["last_learning_date"] >= unified["hire_date"])
    ).all()


def test_vended_views_reconcile(data):
    silver_learning, _ = quarantine_learning(
        data["learning"], data["employees"], data["skills"]
    )
    silver_employees, _ = quarantine_employees(data["employees"], data["roles"])
    unified = build_unified_model(
        silver_employees,
        data["roles"],
        data["employee_skills"],
        data["skills"],
        silver_learning,
    )
    analytics = build_analytics_view(unified)
    operational = build_operational_view(unified)
    assert len(operational) == 59
    assert operational["employee_id"].is_unique
    assert int(analytics["headcount"].sum()) == 59
    assert len(analytics) <= 5  # one row per department present
    recon = check_unified_reconciliation(unified, silver_learning, analytics)
    assert recon.passed is True


def test_talent_stream_exactly_once():
    events = generate_talent_events()
    assert len(events) == 125  # 120 + 3 duplicates + 2 late
    result = run_talent_stream(events)
    assert len(result["accepted"]) == 120
    assert len(result["late"]) == 2
    assert len(result["duplicates"]) == 3
    assert result["accepted"]["event_id"].is_unique
    assert set(result["late"]["event_id"]) == {"T90001", "T90002"}
    assert result["checkpoint"].last_offset == 124


def test_batch_load_dedup(data):
    loaded, duplicates = load_learning_batch(data["learning"])
    assert len(duplicates) == 2  # the two planted duplicate record_ids
    assert len(loaded) == 180
    assert loaded["record_id"].is_unique


def test_query_tuning_demo(data):
    silver_learning, _ = quarantine_learning(
        data["learning"], data["employees"], data["skills"]
    )
    silver_employees, _ = quarantine_employees(data["employees"], data["roles"])
    result = tune_query_demo(silver_learning, silver_employees)
    assert result["rows"] >= 50000
    assert result["employees"] == 59
    assert result["results_match"] is True
    assert result["fast_ms"] < result["slow_ms"]
    assert result["speedup"] > 1.0


def test_generation_is_deterministic():
    first = generate_talent()
    second = generate_talent()
    for key in first:
        pd.testing.assert_frame_equal(first[key], second[key])
    pd.testing.assert_frame_equal(generate_talent_events(), generate_talent_events())
