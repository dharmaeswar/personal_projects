"""Tests for storage tiering, quotas/capacity, and I/O telemetry."""

from datetime import datetime, timezone, timedelta

from llm_data_infra import tiering, quotas, telemetry


def _obj(name, kind="dataset", size=1024, reads=0, tier="SHARED_FS",
         team="team-a", last_read="2026-11-20T00:00:00+00:00"):
    return {"name": name, "kind": kind, "size_bytes": size,
            "reads_last_day": reads, "current_tier": tier,
            "team": team, "last_read_at": last_read}


# --- Tiering ---

def test_latest_checkpoint_stays_on_nvme():
    assert tiering.place_object("checkpoint", 5 * 1024 ** 3, 0,
                                is_latest_checkpoint=True) == "NVME"


def test_hot_dataset_goes_to_nvme_and_cold_large_to_object():
    assert tiering.place_object("dataset", 1024, 80) == "NVME"
    assert tiering.place_object("dataset", 20 * 1024 ** 3, 0) == "OBJECT"


def test_snapshot_goes_to_archive():
    assert tiering.place_object("snapshot", 1024, 100) == "ARCHIVE"


def test_checkpoint_tiering_by_step():
    assert tiering.tier_for_checkpoint(100, 100, 0) == "NVME"
    assert tiering.tier_for_checkpoint(99, 100, 0) == "SHARED_FS"
    assert tiering.tier_for_checkpoint(90, 100, 0) == "OBJECT"


def test_plan_moves_only_misplaced_objects_hot_first():
    objs = [_obj("cold-on-nvme", reads=0, tier="NVME"),
            _obj("hot-on-object", reads=90, tier="OBJECT"),
            _obj("already-right", reads=20, tier="SHARED_FS")]
    moves = tiering.plan_moves(objs)
    assert [m["name"] for m in moves] == ["hot-on-object", "cold-on-nvme"]
    assert moves[0]["to"] == "NVME"


def test_tier_usage_pct_full():
    usage = tiering.tier_usage([_obj("a", size=1024 ** 4, tier="NVME")])
    assert usage["NVME"]["bytes"] == 1024 ** 4
    assert usage["NVME"]["pct_full"] == 50.0


def test_estimated_read_ms_faster_on_nvme():
    assert tiering.estimated_read_ms("NVME", 1024 ** 3) < \
        tiering.estimated_read_ms("OBJECT", 1024 ** 3)


# --- Quotas ---

def test_quota_allows_within_and_refuses_over():
    q = {"team-a": 1000}
    usage = {"team-a": {"bytes": 800, "objects": 2}}
    assert quotas.check_quota("team-a", q, usage, 200)["allowed"] is True
    denied = quotas.check_quota("team-a", q, usage, 201)
    assert denied["allowed"] is False
    assert "exceed quota" in denied["reason"]


def test_quota_refuses_unregistered_team():
    result = quotas.check_quota("team-x", {"team-a": 1000}, {}, 10)
    assert result["allowed"] is False


def test_attribute_usage_sums_per_team():
    usage = quotas.attribute_usage([_obj("a", size=100, team="team-a"),
                                    _obj("b", size=50, team="team-b"),
                                    _obj("c", size=25, team="team-a")])
    assert usage["team-a"]["bytes"] == 125
    assert usage["team-b"]["objects"] == 1


def test_stale_objects_excludes_checkpoints():
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    objs = [_obj("old-dataset", last_read="2026-10-01T00:00:00+00:00"),
            _obj("old-ckpt", kind="checkpoint",
                 last_read="2026-10-01T00:00:00+00:00"),
            _obj("fresh", last_read="2026-11-27T00:00:00+00:00")]
    stale = quotas.stale_objects(objs, 30, now)
    assert [o["name"] for o in stale] == ["old-dataset"]


def test_forecast_full_days():
    assert quotas.forecast_full_days(800, 1000, 100) == 2.0
    assert quotas.forecast_full_days(1000, 1000, 100) == 0.0
    assert quotas.forecast_full_days(800, 1000, 0) is None


def test_cleanup_plan_frees_stale_bytes():
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    objs = [_obj("stale-big", size=500, team="team-a",
                 last_read="2026-10-01T00:00:00+00:00"),
            _obj("fresh", size=100, team="team-a",
                 last_read="2026-11-27T00:00:00+00:00")]
    plan = quotas.cleanup_plan(objs, 30, {"team-a": 10000}, now)
    assert plan["freed_bytes"] == 500
    assert plan["by_team"] == {"team-a": 500}
    assert [o["name"] for o in plan["to_delete"]] == ["stale-big"]


# --- Telemetry ---

def _events():
    events = []
    for _ in range(12):
        telemetry.record_event(events, "read", "hot-set", "OBJECT",
                               1024, 30.0)
    telemetry.record_event(events, "read", "cold-set", "NVME", 1024, 0.2)
    telemetry.record_event(events, "checkpoint_restore", "ckpt-100",
                           "OBJECT", 5 * 1024 ** 3, 9000.0)
    telemetry.record_event(events, "read", "stall-set", "SHARED_FS",
                           1024, 60.0, metadata_ops=1200)
    return events


def test_hot_cold_split():
    split = telemetry.hot_cold(_events())
    assert split["hot"] == ["hot-set"]
    assert "cold-set" in split["cold"]


def test_find_stalls_flags_slow_restore():
    stalls = telemetry.find_stalls(_events(), {"NVME": 0.1, "SHARED_FS": 2.0,
                                              "OBJECT": 25.0, "ARCHIVE": 900.0})
    names = [s["name"] for s in stalls]
    assert "ckpt-100" in names
    assert "stall-set" in names
    assert "hot-set" not in names


def test_metadata_pressure_flags_busy_tier():
    pressure = telemetry.metadata_pressure(_events())
    assert pressure["pressured_tiers"] == ["SHARED_FS"]


def test_placement_suggestions_cover_hot_cold_and_restore():
    suggestions = telemetry.placement_suggestions(_events())
    text = " ".join(suggestions)
    assert "hot-set" in text and "cold-set" in text and "ckpt-100" in text


def test_summary_counts_events_and_kinds():
    result = telemetry.summary(_events(), {"NVME": 0.1, "SHARED_FS": 2.0,
                                          "OBJECT": 25.0, "ARCHIVE": 900.0})
    assert result["events"] == 15
    assert result["by_kind"]["read"] == 14
    assert len(result["stalls"]) == 2
