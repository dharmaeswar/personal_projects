from datetime import datetime, timedelta, timezone

from prediction_markets.cleanse import cleanse
from prediction_markets.ingest import generate_feed
from prediction_markets.store import read_all, read_asof, write_store


def _records():
    feed = generate_feed()
    records, _ = cleanse(feed)
    return records


def test_store_round_trip(tmp_path):
    records = _records()
    manifest = write_store(records, str(tmp_path))
    assert len(manifest) == 12  # one partition per event
    assert sum(m["rows"] for m in manifest) == len(records)
    back = read_all(str(tmp_path))
    assert len(back) == len(records)
    assert back[0].fair_home == records[0].fair_home


def test_read_asof_never_sees_future(tmp_path):
    records = _records()
    write_store(records, str(tmp_path))
    cutoff = datetime(2026, 11, 20, 12, 30, tzinfo=timezone.utc)
    asof = read_asof(str(tmp_path), "NFL-001", cutoff)
    assert asof, "expected rows at or before the cutoff"
    assert all(r.ts <= cutoff for r in asof)
    # 7 snapshots (12:00..12:30) x 3 books, minus any quarantined row.
    assert len(asof) <= 21
    full = read_asof(str(tmp_path), "NFL-001",
                     datetime(2026, 11, 20, 23, 59, tzinfo=timezone.utc))
    assert len(full) >= len(asof)
