from datetime import datetime, timedelta, timezone

import pytest

from prediction_markets.cleanse import cleanse, remove_vig
from prediction_markets.ingest import Snapshot, generate_feed


def _snap(ts, home=-110, away=100, event="NFL-001", book="BookA"):
    return Snapshot(event, book, ts, home, away)


def test_remove_vig_sums_to_one():
    fh, fa, over = remove_vig(0.55, 0.50)
    assert fh + fa == pytest.approx(1.0)
    assert over == pytest.approx(0.05)


def test_remove_vig_rejects_zero():
    with pytest.raises(ValueError):
        remove_vig(0.0, 0.0)


def test_cleanse_keeps_fair_probs_summing_to_one():
    base = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    rows = [_snap(base + timedelta(minutes=5 * i)) for i in range(4)]
    kept, report = cleanse(rows)
    assert report.kept == 4
    for rec in kept:
        assert rec.fair_home + rec.fair_away == pytest.approx(1.0)
        assert 0 < rec.fair_home < 1


def test_cleanse_quarantines_duplicates_missing_and_stale():
    feed = generate_feed()
    kept, report = cleanse(feed)
    assert report.total == 866
    assert report.duplicates == 2
    assert report.missing_odds == 2
    assert report.stale == 1
    assert report.kept == 861
    assert len(report.quarantined) == 5


def test_cleanse_never_silently_drops():
    feed = generate_feed()
    kept, report = cleanse(feed)
    assert report.kept + len(report.quarantined) == report.total
