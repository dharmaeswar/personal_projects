"""Tests for the robotaxi performance telemetry analysis."""
import math

import pytest

from robotaxi_telemetry.data import (
    INTERVENTION_TYPES,
    generate_trips,
    to_rows,
)
from robotaxi_telemetry.metrics import (
    availability_proxy,
    intervention_rate_per_1k_miles,
    kpi_by_release,
    kpi_summary,
    mean_recovery_min,
    mission_completion_rate,
    remote_assistance_rate,
)
from robotaxi_telemetry.stats import (
    compare_rates,
    poisson_rate_ci,
    poisson_rate_ci_per_1k,
)
from run_analysis import analyse


def _rows(n=600, seed=7):
    return to_rows(generate_trips(n, seed))


def test_generator_is_seeded_and_deterministic():
    a = generate_trips(100, seed=3)
    b = generate_trips(100, seed=3)
    assert [(t.trip_id, t.miles, t.interventions) for t in a] == [
        (t.trip_id, t.miles, t.interventions) for t in b
    ]
    c = generate_trips(100, seed=4)
    assert [t.miles for t in a] != [t.miles for t in c]


def test_generator_counts_and_ranges():
    trips = generate_trips(200, seed=1)
    assert len(trips) == 200
    assert all(t.miles > 0 and t.duration_min > 0 for t in trips)
    assert all(set(t.interventions) == set(INTERVENTION_TYPES) for t in trips)
    assert all(v >= 0 for t in trips for v in t.interventions.values())
    assert all(t.recovery_min >= 0 for t in trips)


def test_rows_flatten_interventions():
    rows = _rows(50)
    assert len(rows) == 50
    for r in rows:
        assert r["interventions_total"] == sum(
            r[f"interventions_{k}"] for k in INTERVENTION_TYPES
        )


def test_intervention_rate_scales_with_miles():
    rows = [
        {"miles": 1000.0, "interventions_total": 5},
        {"miles": 1000.0, "interventions_total": 3},
    ]
    assert intervention_rate_per_1k_miles(rows) == pytest.approx(4.0)


def test_intervention_rate_empty_is_zero():
    assert intervention_rate_per_1k_miles([]) == 0.0


def test_mission_completion_and_recovery():
    rows = [
        {"mission_completed": 1, "interventions_total": 0, "recovery_min": 0.0},
        {"mission_completed": 0, "interventions_total": 2, "recovery_min": 10.0},
        {"mission_completed": 1, "interventions_total": 1, "recovery_min": 20.0},
    ]
    assert mission_completion_rate(rows) == pytest.approx(2 / 3)
    assert mean_recovery_min(rows) == pytest.approx(15.0)
    assert remote_assistance_rate(
        [{**r, "remote_assistance": 1} for r in rows[:1]]
        + [{**r, "remote_assistance": 0} for r in rows[1:]]
    ) == pytest.approx(1 / 3)


def test_availability_proxy_counts_clean_trips():
    rows = [
        {"interventions_total": 0, "recovery_min": 0.0},
        {"interventions_total": 1, "recovery_min": 5.0},
        {"interventions_total": 0, "recovery_min": 0.0},
    ]
    assert availability_proxy(rows) == pytest.approx(2 / 3)


def test_kpi_summary_keys_and_types():
    summary = kpi_summary(_rows())
    assert summary["trips"] == 600
    assert summary["miles"] > 0
    assert 0 <= summary["mission_completion_rate"] <= 1
    assert 0 <= summary["availability_proxy"] <= 1
    assert set(summary["by_type_per_1k_miles"]) == set(INTERVENTION_TYPES)


def test_kpi_by_release_covers_all_releases():
    by_rel = kpi_by_release(_rows())
    assert set(by_rel) == {"2026.09", "2026.10", "2026.11"}
    assert sum(v["trips"] for v in by_rel.values()) == 600


def test_later_release_has_lower_intervention_rate_in_synthetic_data():
    by_rel = kpi_by_release(_rows(1200, seed=42))
    rates = [by_rel[r]["interventions_per_1k_miles"] for r in sorted(by_rel)]
    assert rates[0] > rates[1] > rates[2]


def test_poisson_ci_contains_true_rate_and_widens_with_less_data():
    # 100 events in 10,000 miles -> true rate 10 per 1k miles.
    lo, hi = poisson_rate_ci(100, 10.0)
    assert lo < 10.0 < hi
    lo_small, hi_small = poisson_rate_ci(10, 1.0)
    assert (hi_small - lo_small) > (hi - lo)


def test_poisson_ci_zero_count():
    lo, hi = poisson_rate_ci(0, 5.0)
    assert lo == 0.0
    assert hi == pytest.approx(-math.log(0.025) / 5.0)


def test_poisson_ci_per_1k_matches_unit_ci():
    lo1, hi1 = poisson_rate_ci_per_1k(40, 2000.0)
    lo2, hi2 = poisson_rate_ci(40, 2.0)
    assert (lo1, hi1) == pytest.approx((lo2, hi2))


def test_poisson_ci_rejects_bad_exposure():
    with pytest.raises(ValueError):
        poisson_rate_ci(5, 0.0)


def test_compare_rates_equal_rates_not_significant():
    res = compare_rates(50, 5000.0, 50, 5000.0)
    assert res["p_value"] == pytest.approx(1.0, abs=0.01)
    assert res["significant_95"] is False
    assert res["rate_ratio"] == pytest.approx(1.0)


def test_compare_rates_big_drop_is_significant():
    res = compare_rates(100, 5000.0, 20, 5000.0)
    assert res["p_value"] < 0.05
    assert res["significant_95"] is True
    assert res["rate_ratio"] == pytest.approx(0.2)


def test_compare_rates_no_events():
    res = compare_rates(0, 1000.0, 0, 1000.0)
    assert res["p_value"] == 1.0
    assert res["significant_95"] is False


def test_analyse_end_to_end():
    result = analyse(600, seed=7)
    assert result["overall"]["trips"] == 600
    assert len(result["overall"]["interventions_per_1k_miles_ci95"]) == 2
    lo, hi = result["overall"]["interventions_per_1k_miles_ci95"]
    assert lo < result["overall"]["interventions_per_1k_miles"] < hi
    assert len(result["release_comparisons"]) == 2
    assert len(result["by_road"]) == 3
