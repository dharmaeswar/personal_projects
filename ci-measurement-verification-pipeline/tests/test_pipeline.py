"""Tests for the C&I measurement & verification pipeline."""

from mv_pipeline.baseline import build_baseline
from mv_pipeline.marts import mart_payments, mart_site_event_summary
from mv_pipeline.performance import event_performance, payment_for
from mv_pipeline.quality import run_quality_checks
from mv_pipeline.readings import (EVENT_DATE, SITES, generate_readings)
from mv_pipeline.staging import stage_readings


def _staged():
    staged, quarantine, stats = stage_readings(generate_readings())
    return staged, quarantine, stats


def test_raw_count_is_deterministic():
    assert len(generate_readings()) == 3177  # 3168 base + 6 dup + 3 neg


def test_staging_removes_duplicates_and_quarantines_bad_rows():
    _, quarantine, stats = _staged()
    assert stats["raw"] == 3177
    # 3168 interval readings staged; 6 duplicates dropped, 3 negative
    # readings quarantined.
    assert stats["staged"] == 3168
    assert stats["duplicates"] == 6
    assert stats["quarantined"] == 3
    assert all(q["reason"] == "invalid kw" for q in quarantine)


def test_staging_flags_late_arrivals():
    _, _, stats = _staged()
    assert stats["late_arrivals"] == 2


def test_staging_is_idempotent():
    staged, _, _ = _staged()
    keys = {(r["site_id"], r["timestamp"]) for r in staged}
    _, _, restats = stage_readings(generate_readings(),
                                   existing_keys=keys)
    assert restats["staged"] == 0
    # Every non-quarantined raw row matches an already-staged key:
    # 3177 raw - 3 quarantined.
    assert restats["already_loaded"] == 3174


def test_unknown_site_quarantined():
    staged, quarantine, stats = stage_readings(
        [{"site_id": "SITE-Z", "timestamp": "2026-06-15T14:00:00+00:00",
          "kw": 10.0, "arrived_at": "2026-06-15T14:30:00+00:00"}])
    assert staged == []
    assert quarantine[0]["reason"] == "unknown site_id"
    assert stats["quarantined"] == 1


def test_naive_timestamp_treated_as_utc():
    staged, _, _ = stage_readings(
        [{"site_id": "SITE-A", "timestamp": "2026-06-15T14:00:00",
          "kw": 10.0, "arrived_at": "2026-06-15T14:30:00"}])
    assert staged[0]["timestamp"] == "2026-06-15T14:00:00+00:00"


def test_baseline_is_same_interval_average():
    staged, _, _ = _staged()
    baseline = build_baseline(staged)
    # 3 sites x 96 intervals, one baseline per (site, interval).
    assert len(baseline) == 3 * 96
    # Interval 56 is 14:00; SITE-A baseline sits near its base load.
    assert 200.0 < baseline[("SITE-A", 56)] < 240.0


def test_baseline_ignores_event_day():
    staged, _, _ = _staged()
    baseline = build_baseline(staged)
    # SITE-A curtailed ~41 kW during the event; its baseline must not
    # include the curtailed event-day readings.
    assert baseline[("SITE-A", 56)] > 200.0


def test_event_performance_curtailed_sites():
    staged, _, _ = _staged()
    performance = event_performance(build_baseline(staged), staged)
    assert performance["SITE-A"]["intervals"] == 8
    assert 38.0 < performance["SITE-A"]["curtailed_kw"] < 45.0
    assert 16.0 < performance["SITE-B"]["curtailed_kw"] < 21.0
    # SITE-C did not curtail; its small residual is baseline noise only.
    assert performance["SITE-C"]["curtailed_kw"] < 2.0


def test_site_c_no_curtailment_no_payment():
    staged, _, _ = _staged()
    performance = event_performance(build_baseline(staged), staged)
    # Only baseline noise: a few dollars at most, not a real curtailment.
    assert performance["SITE-C"]["curtailed_kwh"] < 3.0
    assert performance["SITE-C"]["payment_usd"] < 15.0


def test_payments_add_up():
    staged, _, _ = _staged()
    performance = event_performance(build_baseline(staged), staged)
    total = payment_for(performance)
    assert total == round(sum(p["payment_usd"]
                              for p in performance.values()), 2)
    assert total > 0


def test_over_use_never_pays_negative():
    staged, _, _ = _staged()
    performance = event_performance(build_baseline(staged), staged)
    for p in performance.values():
        assert p["payment_usd"] >= 0
        assert p["curtailed_kw"] >= 0


def test_quality_checks_catch_gaps():
    staged, _, _ = _staged()
    # Drop one interval for SITE-A on the event day.
    cut = [r for r in staged
           if not (r["site_id"] == "SITE-A"
                   and r["timestamp"].startswith("2026-06-15T14:00"))]
    checks = run_quality_checks(cut, [])
    assert checks["gaps"]["passed"] is False
    assert checks["gaps"]["sites_with_gaps"]["SITE-A"][0][
        "missing_intervals"] == 1


def test_quality_checks_pass_on_clean_batch():
    staged, quarantine, _ = _staged()
    checks = run_quality_checks(staged, quarantine)
    assert checks["gaps"]["passed"] is True
    assert checks["unknown_sites"]["passed"] is True
    assert checks["late_arrivals"]["count"] == 2
    assert checks["quarantined"]["count"] == 3


def test_marts_have_one_row_per_site():
    staged, _, _ = _staged()
    performance = event_performance(build_baseline(staged), staged)
    summary = mart_site_event_summary(performance, EVENT_DATE)
    payments = mart_payments(performance, EVENT_DATE)
    assert len(summary) == len(SITES) == 3
    assert len(payments) == 3
    assert {r["site_id"] for r in payments} == set(SITES)
    assert summary[0]["event_date"] == "2026-06-15"


def test_payment_traceable_to_intervals():
    staged, _, _ = _staged()
    performance = event_performance(build_baseline(staged), staged)
    p = performance["SITE-A"]
    assert p["payment_usd"] == round(
        p["curtailed_kwh"] * SITES["SITE-A"]["rate_usd_per_kwh"], 2)
