"""Data-quality checks for media session events.

Bad rows are quarantined with a reason, never dropped silently — the same
contract a Delta Lake bronze layer enforces with expectations before a row
reaches silver.
"""
from __future__ import annotations

import pandas as pd

REQUIRED_FIELDS = (
    "event_id", "session_id", "user_id", "title_id", "device", "region",
    "app", "event_type", "event_ts", "playhead_seconds", "bitrate_kbps",
)
VALID_EVENT_TYPES = (
    "session_start", "heartbeat", "pause", "resume", "seek",
    "ad_start", "ad_end", "error", "session_end",
)
VALID_DEVICES = ("tv", "mobile", "web", "tablet")
MAX_BITRATE_KBPS = 25000
MAX_PLAYHEAD_SECONDS = 24 * 3600


def check_event(event: dict) -> list[str]:
    """Return the list of quality issues for one event (empty = clean)."""
    issues: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in event or event[f] is None or event[f] == "":
            issues.append(f"missing:{f}")
    if issues:
        return issues
    if event["event_type"] not in VALID_EVENT_TYPES:
        issues.append(f"bad_event_type:{event['event_type']}")
    if event["device"] not in VALID_DEVICES:
        issues.append(f"bad_device:{event['device']}")
    try:
        if float(event["playhead_seconds"]) < 0:
            issues.append("negative_playhead")
        elif float(event["playhead_seconds"]) > MAX_PLAYHEAD_SECONDS:
            issues.append("playhead_too_large")
    except (TypeError, ValueError):
        issues.append("bad_playhead")
    try:
        if float(event["bitrate_kbps"]) < 0:
            issues.append("negative_bitrate")
        elif float(event["bitrate_kbps"]) > MAX_BITRATE_KBPS:
            issues.append("bitrate_too_large")
    except (TypeError, ValueError):
        issues.append("bad_bitrate")
    return issues


def cleanse(events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split events into (good, quarantined); quarantined rows carry a reason.

    Also de-duplicates on event_id, keeping the first occurrence — the
    local mirror of ``dropDuplicates(["event_id"])`` in Structured
    Streaming. Duplicate rows land in quarantine with reason
    ``duplicate_event_id``.
    """
    good: list[dict] = []
    quarantined: list[dict] = []
    seen: set[str] = set()
    for event in events:
        eid = event.get("event_id")
        if eid in seen:
            bad = dict(event)
            bad["quarantine_reason"] = "duplicate_event_id"
            quarantined.append(bad)
            continue
        seen.add(eid)
        issues = check_event(event)
        if issues:
            bad = dict(event)
            bad["quarantine_reason"] = ";".join(issues)
            quarantined.append(bad)
        else:
            good.append(event)
    return good, quarantined


def quarantine_summary(quarantined: list[dict]) -> pd.DataFrame:
    """Count quarantined rows by reason, for the run manifest."""
    if not quarantined:
        return pd.DataFrame(columns=["quarantine_reason", "count"])
    df = pd.DataFrame(quarantined)
    return (df.groupby("quarantine_reason").size().reset_index(name="count")
            .sort_values("count", ascending=False).reset_index(drop=True))
