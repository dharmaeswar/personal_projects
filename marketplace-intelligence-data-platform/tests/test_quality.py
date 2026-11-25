"""Tests for data quality: quarantine reasons, delayed-but-loaded
rows, and source-to-warehouse reconciliation."""

from marketintel.quality import reconcile, run_quality_checks

BASE = {"competitor": "lyft", "zone": "downtown", "snapshot_date": "2026-11-24",
        "price_usd": 17.25, "service": "ride"}


def test_clean_rows_all_load():
    loaded, report = run_quality_checks(
        [dict(BASE), {**BASE, "zone": "airport", "price_usd": 30.5}],
        known_zones={"downtown", "airport"},
    )
    assert report.loaded == 2
    assert report.quarantined == []


def test_duplicate_natural_key_quarantined():
    _, report = run_quality_checks([dict(BASE), dict(BASE)])
    assert report.duplicates == 1
    assert report.loaded == 1
    assert report.quarantined[0][1] == "duplicate natural key"


def test_missing_price_quarantined():
    row = dict(BASE, price_usd=None)
    _, report = run_quality_checks([row])
    assert report.missing == 1
    assert report.loaded == 0


def test_negative_price_quarantined():
    row = dict(BASE, price_usd=-5.0)
    _, report = run_quality_checks([row])
    assert report.inconsistent == 1
    assert report.quarantined[0][1] == "price_usd <= 0"


def test_non_numeric_price_quarantined_not_crash():
    row = dict(BASE, price_usd="abc")
    _, report = run_quality_checks([row])
    assert report.inconsistent == 1
    assert report.loaded == 0


def test_unknown_zone_quarantined():
    _, report = run_quality_checks([dict(BASE, zone="harbor")],
                                   known_zones={"downtown", "airport"})
    assert report.inconsistent == 1
    assert "unknown zone" in report.quarantined[0][1]


def test_late_row_is_delayed_but_still_loaded():
    loaded, report = run_quality_checks(
        [dict(BASE, snapshot_date="2026-11-20")],
        watermark_date="2026-11-24",
    )
    assert report.delayed == 1
    assert len(loaded) == 1  # late data is valid data


def test_reconcile_matches_and_mismatches():
    ok = reconcile([dict(BASE)], 1, 17.25)
    assert ok.ok
    bad = reconcile([dict(BASE)], 2, 17.25)
    assert not bad.rows_match and not bad.ok
    bad_total = reconcile([dict(BASE)], 1, 99.99)
    assert not bad_total.totals_match
