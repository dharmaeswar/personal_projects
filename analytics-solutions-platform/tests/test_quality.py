import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.quality import (check_completeness, check_freshness,
                                          check_ranges, check_referential_integrity,
                                          check_uniqueness, run_quality_gate)


def test_gate_passes_on_clean_data():
    rows = [{"policy_id": "P1", "premium_annual": 100.0}, {"policy_id": "P2", "premium_annual": 200.0}]
    gate = run_quality_gate(rows, required=["policy_id", "premium_annual"], unique_key="policy_id",
                            range_checks=[("premium_annual", 0, 1_000_000)],
                            as_of=date(2026, 11, 20), max_data_date=date(2026, 11, 20), sla_days=1)
    assert gate.passed
    assert gate.failures() == []


def test_gate_names_each_failure():
    rows = [{"policy_id": "P1", "premium_annual": -5.0},
            {"policy_id": "P1", "premium_annual": 100.0},
            {"policy_id": "P3", "premium_annual": None}]
    gate = run_quality_gate(rows, required=["policy_id", "premium_annual"], unique_key="policy_id",
                            range_checks=[("premium_annual", 0, 1_000_000)])
    assert not gate.passed
    failed = {c.name for c in gate.failures()}
    assert failed == {"completeness", "uniqueness", "range"}


def test_referential_integrity_catches_orphan():
    facts = [{"holder_key": 1}, {"holder_key": 9}]
    result = check_referential_integrity(facts, {"holder": {1, 2}}, {"holder_key": "holder"})
    assert not result.passed
    assert "9" in result.detail


def test_freshness_sla():
    assert check_freshness(date(2026, 11, 20), date(2026, 11, 19), 1).passed
    assert not check_freshness(date(2026, 11, 20), date(2026, 11, 18), 1).passed


def test_individual_checks():
    assert check_completeness([{"a": 1}], ["a"]).passed
    assert not check_completeness([{"a": ""}], ["a"]).passed
    assert check_uniqueness([{"k": 1}, {"k": 2}], "k").passed
    assert not check_uniqueness([{"k": 1}, {"k": 1}], "k").passed
    assert check_ranges([{"v": 5}], "v", 0, 10).passed
    assert not check_ranges([{"v": 50}], "v", 0, 10).passed
