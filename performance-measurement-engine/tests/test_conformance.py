"""Tests for the versioned conformance harness and run pinning."""

from decimal import Decimal

from perf.conformance import (
    ENGINE_VERSION, MEASURE_VERSIONS, GOLDEN_VECTORS,
    input_hash, data_snapshot_hash, pin_run, run_conformance,
)


def test_run_conformance_all_pass():
    report = run_conformance()
    assert report["failed"] == []
    assert report["engine_version"] == ENGINE_VERSION
    assert len(report["passed"]) == len(GOLDEN_VECTORS) + 5  # 7 vectors + 5 invariants
    assert report["summary"] == "%d passed, 0 failed" % len(report["passed"])


def test_measure_versions_cover_all_measures():
    for name in ("irr_decimal", "modified_dietz_decimal", "ks_pme",
                 "direct_alpha", "long_nickels_pme", "chained_index"):
        assert name in MEASURE_VERSIONS


def test_input_hash_is_order_independent():
    request_a = {"fund": "F1", "measures": ["irr_decimal", "ks_pme"]}
    request_b = {"measures": ["irr_decimal", "ks_pme"], "fund": "F1"}
    assert input_hash(request_a) == input_hash(request_b)


def test_input_hash_changes_with_content():
    assert input_hash({"a": 1}) != input_hash({"a": 2})


def test_pin_run_reproducible_and_sensitive():
    fund = {"flows": [["0", "100"], ["1", "-121"]],
            "index_levels": [["0", "100"], ["1", "110"]]}
    request = {"measures": ["ks_pme"]}
    pin_a = pin_run(fund, request)
    pin_b = pin_run(fund, request)
    assert pin_a == pin_b
    assert pin_a.engine_version == ENGINE_VERSION
    assert pin_a.measure_versions["ks_pme"] == "1.0.0"
    changed = dict(fund)
    changed["flows"] = [["0", "100"], ["1", "-122"]]
    pin_c = pin_run(changed, request)
    assert pin_c.data_snapshot != pin_a.data_snapshot
    assert pin_c.request_hash == pin_a.request_hash


def test_snapshot_hash_differs_across_funds():
    assert data_snapshot_hash({"fund": "A"}) != data_snapshot_hash({"fund": "B"})
