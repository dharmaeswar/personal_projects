"""Demo: tiering, quotas and I/O telemetry for an AI data platform.

Seeds a small synthetic fleet of datasets and checkpoints across three
research teams, places each object on its ideal storage tier, enforces
quotas, plans stale-data cleanup, and analyses I/O telemetry to suggest
placement fixes. Prints a short report; writes tiering_demo_report.json.
All data is synthetic demo data.
"""

import json
import os
from datetime import datetime, timezone

from llm_data_infra import tiering, quotas, telemetry

GB = 1024 ** 3
NOW = datetime(2026, 11, 28, tzinfo=timezone.utc)

OBJECTS = [
    {"name": "webtext-v3", "kind": "dataset", "size_bytes": 800 * GB,
     "reads_last_day": 120, "current_tier": "OBJECT", "team": "team-llm",
     "last_read_at": "2026-11-28T00:00:00+00:00"},
    {"name": "image-pairs-v2", "kind": "dataset", "size_bytes": 300 * GB,
     "reads_last_day": 8, "current_tier": "SHARED_FS", "team": "team-llm",
     "last_read_at": "2026-11-27T00:00:00+00:00"},
    {"name": "old-crawl-v1", "kind": "dataset", "size_bytes": 900 * GB,
     "reads_last_day": 0, "current_tier": "SHARED_FS", "team": "team-rl",
     "last_read_at": "2026-09-15T00:00:00+00:00"},
    {"name": "ckpt-step-100", "kind": "checkpoint", "size_bytes": 120 * GB,
     "reads_last_day": 2, "current_tier": "OBJECT", "team": "team-llm",
     "last_read_at": "2026-11-28T00:00:00+00:00", "is_latest_checkpoint": True,
     "step": 100, "latest_step": 100},
    {"name": "ckpt-step-99", "kind": "checkpoint", "size_bytes": 120 * GB,
     "reads_last_day": 1, "current_tier": "NVME", "team": "team-llm",
     "last_read_at": "2026-11-27T00:00:00+00:00",
     "step": 99, "latest_step": 100},
    {"name": "ckpt-step-80", "kind": "checkpoint", "size_bytes": 120 * GB,
     "reads_last_day": 0, "current_tier": "SHARED_FS", "team": "team-rl",
     "last_read_at": "2026-11-20T00:00:00+00:00",
     "step": 80, "latest_step": 100},
    {"name": "rl-env-snapshots", "kind": "snapshot", "size_bytes": 40 * GB,
     "reads_last_day": 0, "current_tier": "OBJECT", "team": "team-rl",
     "last_read_at": "2026-10-01T00:00:00+00:00"},
    {"name": "scratch-run-441", "kind": "scratch", "size_bytes": 60 * GB,
     "reads_last_day": 3, "current_tier": "NVME", "team": "team-agents",
     "last_read_at": "2026-11-28T00:00:00+00:00"},
]

QUOTAS = {"team-llm": 1200 * GB, "team-rl": 1000 * GB, "team-agents": 200 * GB}


def main() -> dict:
    moves = tiering.plan_moves(OBJECTS)
    placed = []
    for obj in OBJECTS:
        if obj["kind"] == "checkpoint" and "step" in obj:
            ideal = tiering.tier_for_checkpoint(obj["step"],
                                                obj["latest_step"],
                                                obj["reads_last_day"])
        else:
            ideal = tiering.place_object(obj["kind"], obj["size_bytes"],
                                         obj["reads_last_day"],
                                         obj.get("is_latest_checkpoint", False))
        placed.append({**obj, "current_tier": ideal})
    usage = tiering.tier_usage(placed)
    team_usage = quotas.attribute_usage(placed)
    quota_checks = {team: quotas.check_quota(team, QUOTAS, team_usage, 0)
                    for team in QUOTAS}
    cleanup = quotas.cleanup_plan(OBJECTS, 30, QUOTAS, NOW)
    total = sum(o["size_bytes"] for o in placed)
    capacity = sum(tiering.TIER_CAPACITY_BYTES.values())
    forecast = quotas.forecast_full_days(total, capacity, 5 * 1024 ** 4)

    events: list[dict] = []
    for _ in range(120):
        telemetry.record_event(events, "read", "webtext-v3", "OBJECT",
                               4 * 1024 ** 2, 30.0)
    for _ in range(3):
        telemetry.record_event(events, "read", "old-crawl-v1", "SHARED_FS",
                               4 * 1024 ** 2, 2.5)
    telemetry.record_event(events, "checkpoint_save", "ckpt-step-100",
                           "NVME", 120 * GB, 800.0)
    telemetry.record_event(events, "checkpoint_restore", "ckpt-step-100",
                           "OBJECT", 120 * GB, 9000.0)
    telemetry.record_event(events, "read", "image-pairs-v2", "SHARED_FS",
                           4 * 1024 ** 2, 60.0, metadata_ops=1200)
    io_summary = telemetry.summary(events, tiering.TIER_LATENCY_MS)

    report = {
        "objects": len(OBJECTS),
        "moves_planned": len(moves),
        "moves": moves,
        "tier_usage": usage,
        "team_usage_gb": {t: round(u["bytes"] / GB, 1)
                          for t, u in team_usage.items()},
        "quota_checks": {t: c["allowed"] for t, c in quota_checks.items()},
        "cleanup_freed_gb": round(cleanup["freed_bytes"] / GB, 1),
        "cleanup_by_team_gb": {t: round(b / GB, 1)
                               for t, b in cleanup["by_team"].items()},
        "forecast_full_days_at_5pib_per_day": forecast,
        "io_summary": io_summary,
    }
    path = os.path.join(os.path.dirname(__file__), "tiering_demo_report.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)

    print(f"Objects: {len(OBJECTS)}; moves planned: {len(moves)}")
    for move in moves:
        print(f"  {move['name']}: {move['from']} -> {move['to']}")
    print("Tier usage:")
    for tier, stats in usage.items():
        print(f"  {tier}: {stats['objects']} objects, "
              f"{stats['bytes'] / GB:.0f} GiB ({stats['pct_full']}% full)")
    print(f"Cleanup frees {report['cleanup_freed_gb']} GiB of stale data")
    print(f"Pool full in ~{forecast} days at 5 PiB/day growth")
    print(f"Stalls: {len(io_summary['stalls'])}; "
          f"pressured tiers: {io_summary['metadata']['pressured_tiers']}")
    for suggestion in io_summary["suggestions"]:
        print(f"  SUGGESTION: {suggestion}")
    return report


if __name__ == "__main__":
    main()
