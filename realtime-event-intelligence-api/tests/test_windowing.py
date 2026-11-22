"""Tests for tumbling windows: bucketing, watermark, late events."""

import pytest

from event_intel.windowing import TumblingWindows


def test_events_bucket_into_tumbling_windows():
    windows = TumblingWindows(window_seconds=60.0)
    assert windows.add(5.0, "critical") == "accepted"
    assert windows.add(59.0, "watch") == "accepted"
    assert windows.add(61.0, "info") == "accepted"
    closed = windows.close_all()
    assert [w.window_start for w in closed] == [0.0, 60.0]
    assert closed[0].counts == {"critical": 1, "watch": 1, "info": 0}
    assert closed[0].events == 2
    assert closed[1].counts["info"] == 1


def test_watermark_closes_windows_that_end_before_it():
    windows = TumblingWindows(window_seconds=60.0, allowed_lateness=0.0)
    windows.add(5.0, "info")
    windows.add(130.0, "watch")  # watermark jumps past window [0, 60)
    assert [w.window_start for w in windows.closed_windows] == [0.0]
    assert windows.closed_windows[0].events == 1


def test_late_event_after_allowed_lateness_is_dropped():
    windows = TumblingWindows(window_seconds=60.0, allowed_lateness=10.0)
    windows.add(5.0, "info")
    windows.add(200.0, "watch")  # watermark 200; window [0,60) ends 140 < 190
    assert windows.add(30.0, "critical") == "late"
    assert windows.late_dropped == 1
    assert windows.on_time == 2


def test_event_within_allowed_lateness_is_accepted():
    windows = TumblingWindows(window_seconds=60.0, allowed_lateness=30.0)
    windows.add(5.0, "info")
    windows.add(75.0, "watch")  # watermark 75; window [0,60) ends 60 > 45
    assert windows.add(50.0, "critical") == "accepted"
    assert windows.late_dropped == 0


def test_window_boundaries_are_exact():
    windows = TumblingWindows(window_seconds=60.0)
    windows.add(60.0, "watch")
    closed = windows.close_all()
    assert [w.window_start for w in closed] == [60.0]


def test_invalid_window_size_rejected():
    with pytest.raises(ValueError):
        TumblingWindows(window_seconds=0)


def test_negative_event_time_rejected():
    windows = TumblingWindows()
    with pytest.raises(ValueError):
        windows.add(-1.0, "info")


def test_unknown_band_rejected():
    windows = TumblingWindows()
    with pytest.raises(ValueError):
        windows.add(5.0, "severe")


def test_open_windows_listed_in_order():
    windows = TumblingWindows(window_seconds=60.0, allowed_lateness=300.0)
    windows.add(130.0, "info")
    windows.add(5.0, "watch")
    assert [w.window_start for w in windows.open_windows] == [0.0, 120.0]
