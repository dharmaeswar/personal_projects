import pandas as pd

from personalization_data import events, quality


def _row(**overrides):
    base = {
        "event_id": "E000001", "user_id": "U0001", "content_id": "C0001",
        "event_type": "impression", "event_ts": pd.Timestamp("2026-11-02 10:00"),
        "ingested_at": pd.Timestamp("2026-11-02 10:01"), "device": "ios",
        "surface": "mobile", "country": "US", "genre": "news",
        "title_type": "movie", "content_duration_s": 600, "watch_seconds": None,
    }
    base.update(overrides)
    return base


def test_clean_row_passes():
    assert quality.validate_row(pd.Series(_row())) == []


def test_bad_rows_are_quarantined_with_reasons():
    df = pd.DataFrame([
        _row(),
        _row(event_id="E000002", event_type="mystery_type"),
        _row(event_id="E000003", watch_seconds=-5.0, event_type="view_start"),
        _row(event_id="E000004", watch_seconds=900.0, event_type="view_start"),
        _row(event_id="E000005", user_id=None),
    ])
    clean, quarantined = quality.cleanse(df)
    assert len(clean) == 1
    assert len(quarantined) == 4
    reasons = ";".join(quarantined["quarantine_reason"])
    assert "unknown_event_type" in reasons
    assert "negative_watch_seconds" in reasons
    assert "watch_exceeds_duration" in reasons
    assert "missing_user_id" in reasons


def test_dedupe_keeps_latest_ingest():
    df = pd.DataFrame([
        _row(event_type="view_start", watch_seconds=10.0),
        _row(event_type="view_start", watch_seconds=20.0,
             ingested_at=pd.Timestamp("2026-11-02 10:05")),
    ])
    clean, _ = quality.cleanse(df)
    assert len(clean) == 1
    assert clean.iloc[0]["watch_seconds"] == 20.0


def test_generated_events_cleanse_cleanly_except_redeliveries():
    raw = events.generate_events(n_impressions=100, seed=42)
    clean, quarantined = quality.cleanse(raw)
    assert len(quarantined) == 0
    assert len(clean) == raw["event_id"].nunique()
    report = quality.quality_report(clean, quarantined)
    assert report["quarantine_rate"] == 0.0
    assert report["total_rows"] == len(clean) + len(quarantined)
    assert len(raw) - len(clean) == raw["event_id"].duplicated().sum()  # redeliveries deduped
