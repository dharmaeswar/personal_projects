from event_intel.store import EventStore, fingerprint


def test_fingerprint_ignores_case_and_spacing():
    assert fingerprint("s1", "outage", "Power  Outage") == fingerprint(
        "s1", "outage", "  power outage "
    )


def test_fingerprint_differs_by_source_or_type():
    base = fingerprint("s1", "outage", "power outage")
    assert fingerprint("s2", "outage", "power outage") != base
    assert fingerprint("s1", "weather", "power outage") != base


def test_ingest_stores_event_and_alert_above_threshold():
    store = EventStore()
    result = store.ingest("s1", "outage", "power outage", 82.5, "critical")
    assert result["status"] == "stored"
    assert result["event_id"] == 1
    assert result["alert_id"] == 1
    assert store.counts() == {"events": 1, "alerts": 1, "duplicates_dropped": 0}


def test_ingest_below_threshold_stores_event_without_alert():
    store = EventStore()
    result = store.ingest("s1", "weather", "light rain", 12.0, "info")
    assert result["status"] == "stored"
    assert result["alert_id"] is None
    assert store.counts()["alerts"] == 0


def test_duplicate_is_dropped_and_counted():
    store = EventStore()
    store.ingest("s1", "outage", "power outage", 82.5, "critical")
    result = store.ingest("s1", "outage", "Power Outage", 82.5, "critical")
    assert result["status"] == "duplicate"
    assert store.counts() == {"events": 1, "alerts": 1, "duplicates_dropped": 1}


def test_list_alerts_filters_by_min_severity():
    store = EventStore()
    store.ingest("s1", "outage", "power outage", 82.5, "critical")
    store.ingest("s2", "weather", "heavy rain", 55.0, "watch")
    store.ingest("s3", "weather", "light rain", 12.0, "info")
    all_alerts = store.list_alerts()
    assert [a["severity"] for a in all_alerts] == [82.5, 55.0]
    critical_only = store.list_alerts(min_severity=70)
    assert len(critical_only) == 1
    assert critical_only[0]["event_type"] == "outage"


def test_get_alert_round_trip_and_missing():
    store = EventStore()
    store.ingest("s1", "outage", "power outage", 82.5, "critical")
    alert = store.get_alert(1)
    assert alert is not None
    assert alert["text"] == "power outage"
    assert alert["band"] == "critical"
    assert store.get_alert(999) is None
