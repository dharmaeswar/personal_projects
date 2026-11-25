from order_stream.events import seed_events
from order_stream.quality import cleanse, hierarchy_for, standardize_channel


def test_channel_standardization():
    assert standardize_channel("DRIVE-THRU") == "drive-thru"
    assert standardize_channel("drive thru") == "drive-thru"
    assert standardize_channel("app") == "mobile"
    assert standardize_channel("walk-in") is None


def test_hierarchy_from_master_data():
    assert hierarchy_for("R1001") == ("Chicago", "Midwest")
    assert hierarchy_for("R9999") is None


def test_cleanse_quarantines_bad_rows_with_reasons():
    result = cleanse(seed_events())
    reasons = {reason for _, reason in result.quarantined}
    assert "non_positive_quantity_or_price" in reasons
    assert "unknown_menu_code" in reasons
    assert "total_amount_mismatch" in reasons
    assert result.stats["clean"] > 0
    assert result.stats["clean"] + result.stats["quarantined"] == len({e.order_id for e in seed_events()})


def test_dedup_keeps_latest_event_time():
    from datetime import datetime

    from order_stream.events import OrderEvent

    early = OrderEvent("ORD-1", "R1001", datetime(2026, 11, 20, 11, 0), "counter", "M001", 1, 5.99, 5.99)
    late = OrderEvent("ORD-1", "R1001", datetime(2026, 11, 20, 11, 5), "counter", "M001", 2, 5.99, 11.98)
    result = cleanse([early, late])
    assert len(result.clean) == 1
    assert result.clean[0].quantity == 2
    assert result.clean[0].total_amount == 11.98


def test_clean_rows_have_standardized_channels():
    result = cleanse(seed_events())
    assert all(e.channel.islower() and " " not in e.channel for e in result.clean)
