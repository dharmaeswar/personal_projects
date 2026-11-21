"""Tests for the experimentation guardrails module."""
import math

import pytest

from product_analytics import db, experiments, ingest, seed


def _loaded_conn(count: int = 6000):
    conn = db.connect()
    events = seed.generate_events(count=count)
    ingest.load_raw(conn, events)
    ingest.build_staging(conn)
    return conn


def test_assignment_is_deterministic():
    first = experiments.assign_variant("user_042")
    second = experiments.assign_variant("user_042")
    assert first == second
    assert first in ("control", "treatment")


def test_assignment_split_is_near_even():
    counts = {"control": 0, "treatment": 0}
    for i in range(1, 301):
        counts[experiments.assign_variant(f"user_{i:03d}")] += 1
    # Hash bucketing over 300 users should land close to 50/50.
    assert 120 <= counts["control"] <= 180
    assert 120 <= counts["treatment"] <= 180


def test_assignment_respects_weights():
    variant = experiments.assign_variant("user_001", variants=("a", "b", "c"),
                                         weights=(0.2, 0.3, 0.5))
    assert variant in ("a", "b", "c")
    with pytest.raises(ValueError):
        experiments.assign_variant("user_001", weights=(0.5, 0.6))


def test_chi2_sf_known_values():
    assert experiments.chi2_sf(0.0, 1) == 1.0
    # chi2 = 3.841, df = 1 is the 5% critical value.
    assert abs(experiments.chi2_sf(3.841, 1) - 0.05) < 0.002
    # chi2 = 6.635, df = 1 is the 1% critical value.
    assert abs(experiments.chi2_sf(6.635, 1) - 0.01) < 0.002


def test_srm_passes_on_balanced_split():
    result = experiments.srm_check({"control": 152, "treatment": 148})
    assert result["status"] == "pass"
    assert result["p_value"] > 0.5


def test_srm_fails_on_skewed_split():
    result = experiments.srm_check({"control": 900, "treatment": 100})
    assert result["status"] == "fail"
    assert result["p_value"] < 0.001


def test_compare_proportions_identical_rates():
    out = experiments.compare_proportions(50, 200, 50, 200)
    assert out["lift"] == pytest.approx(0.0)
    assert out["z"] == pytest.approx(0.0)
    assert out["p_value"] == pytest.approx(1.0)


def test_compare_proportions_clear_difference():
    out = experiments.compare_proportions(100, 1000, 150, 1000)
    assert out["lift"] == pytest.approx(0.05)
    assert out["z"] > 3.0
    assert out["p_value"] < 0.01
    assert out["ci_low"] > 0.0  # CI excludes zero


def test_compare_proportions_needs_observations():
    with pytest.raises(ValueError):
        experiments.compare_proportions(0, 0, 5, 10)


def test_assign_users_is_idempotent():
    conn = _loaded_conn()
    first = experiments.assign_users(conn)
    second = experiments.assign_users(conn)
    assert first == second
    assert sum(first.values()) == 300  # every seeded user assigned once


def test_run_experiment_checks_end_to_end():
    conn = _loaded_conn()
    checks = experiments.run_experiment_checks(conn)
    names = [c["check"] for c in checks]
    assert names == ["srm", "preperiod_balance", "postperiod_lift"]
    assert all(c["status"] == "pass" for c in checks)
    rows = conn.execute(
        "SELECT check_name, status FROM experiment_results").fetchall()
    assert len(rows) == 3
    assert all(r[1] == "pass" for r in rows)


def test_run_experiment_checks_fails_on_broken_assignment():
    conn = _loaded_conn()
    experiments.assign_users(conn)
    # Break the assignment: move every treatment user to control.
    conn.execute(
        "UPDATE experiment_assignments SET variant = 'control' "
        "WHERE variant = 'treatment'")
    conn.commit()
    with pytest.raises(RuntimeError, match="srm"):
        experiments.run_experiment_checks(conn)


def test_full_pipeline_includes_experiment_task():
    import run_pipeline
    from product_analytics.orchestration import run_dag

    conn = db.connect()
    events = seed.generate_events(count=6000)
    results = run_dag(conn, run_pipeline.build_tasks(events))
    assert results["experiment_checks"] == "success"
    assert results["publish_catalog"] == "success"
    rows = conn.execute(
        "SELECT COUNT(*) FROM experiment_results WHERE status = 'pass'").fetchone()[0]
    assert rows == 3
