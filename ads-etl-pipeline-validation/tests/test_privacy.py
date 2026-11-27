"""Tests for the privacy-safe reporting gate (ads_etl/privacy.py)."""

from __future__ import annotations

import pytest

from ads_etl.privacy import (
    DEFAULT_MIN_SOURCE_ROWS,
    build_privacy_safe_rollup,
    privacy_summary_lines,
)


def _row(campaign_id, spend=10.0, impressions=100, clicks=5):
    return {
        "event_id": f"e-{campaign_id}-{spend}-{impressions}",
        "campaign_id": campaign_id,
        "impressions": impressions,
        "clicks": clicks,
        "spend_usd": spend,
    }


def test_group_above_threshold_is_published():
    silver = [_row("c1", spend=10.0) for _ in range(6)]
    rollup = build_privacy_safe_rollup(silver, {"c1": "display"})
    assert len(rollup["published"]) == 1
    assert rollup["published"][0]["source_row_count"] == 6
    assert rollup["published"][0]["spend_usd"] == 60.00
    assert rollup["suppressed"] == []
    assert rollup["summary"]["reconciles"] is True


def test_group_below_threshold_is_suppressed_and_listed():
    silver = [_row("c1", spend=10.0) for _ in range(3)]
    silver += [_row("c2", spend=20.0) for _ in range(8)]
    rollup = build_privacy_safe_rollup(silver, {"c1": "video", "c2": "display"})
    assert [g["campaign_id"] for g in rollup["published"]] == ["c2"]
    assert [g["campaign_id"] for g in rollup["suppressed"]] == ["c1"]
    assert "3 found" in rollup["suppressed"][0]["suppression_reason"]
    assert rollup["summary"]["suppressed_groups"] == 1
    assert rollup["summary"]["suppressed_spend_usd"] == 30.00


def test_published_plus_suppressed_reconciles_to_silver():
    silver = [_row("c1", spend=7.5) for _ in range(2)]
    silver += [_row("c2", spend=12.25) for _ in range(9)]
    rollup = build_privacy_safe_rollup(silver, {"c1": "video", "c2": "display"})
    s = rollup["summary"]
    assert s["silver_spend_usd"] == 125.25
    assert s["published_spend_usd"] + s["suppressed_spend_usd"] == 125.25
    assert s["reconciles"] is True


def test_threshold_of_one_publishes_everything():
    silver = [_row("c1", spend=5.0)]
    rollup = build_privacy_safe_rollup(silver, {"c1": "video"}, min_source_rows=1)
    assert rollup["summary"]["published_groups"] == 1
    assert rollup["summary"]["suppressed_groups"] == 0


def test_invalid_threshold_raises():
    with pytest.raises(ValueError):
        build_privacy_safe_rollup([_row("c1")], min_source_rows=0)


def test_unknown_channel_when_no_mapping_given():
    silver = [_row("c9", spend=10.0) for _ in range(5)]
    rollup = build_privacy_safe_rollup(silver)
    assert rollup["published"][0]["channel"] == "unknown"


def test_summary_lines_list_suppressed_groups():
    silver = [_row("c1", spend=10.0) for _ in range(2)]
    rollup = build_privacy_safe_rollup(silver, {"c1": "video"})
    lines = privacy_summary_lines(rollup)
    assert any("Suppressed groups: 1" in line for line in lines)
    assert any("c1" in line and "Suppressed:" in line for line in lines)
    assert any("PASS" in line for line in lines)


def test_default_threshold_is_five():
    assert DEFAULT_MIN_SOURCE_ROWS == 5
