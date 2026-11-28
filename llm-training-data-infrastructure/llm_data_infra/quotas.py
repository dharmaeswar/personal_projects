"""Quotas, capacity and data lifecycle across research teams.

Models the ownership side of the MARS AI Data team: many teams share
one storage pool, so every byte is attributed to a team, each team has
a quota, writes over quota are refused before they land, stale data is
cleaned up on a retention schedule, and capacity is forecast before it
runs out. All data is synthetic demo data.
"""

from datetime import datetime, timezone, timedelta


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def attribute_usage(objects: list[dict]) -> dict:
    """Bytes and object count per owning team."""
    usage: dict[str, dict] = {}
    for obj in objects:
        team = obj["team"]
        entry = usage.setdefault(team, {"bytes": 0, "objects": 0})
        entry["bytes"] += obj["size_bytes"]
        entry["objects"] += 1
    return usage


def check_quota(team: str, quotas: dict, usage: dict, new_bytes: int) -> dict:
    """Decide whether a team may write ``new_bytes`` more.

    Returns {"allowed": bool, "team": str, "used_bytes": int,
    "quota_bytes": int, "after_bytes": int, "reason": str}.
    A write that would exceed the quota is refused, never partially
    applied; a team with no quota entry is refused as unregistered.
    """
    if new_bytes < 0:
        raise ValueError("new_bytes must be >= 0")
    if team not in quotas:
        return {"allowed": False, "team": team, "used_bytes": 0,
                "quota_bytes": 0, "after_bytes": new_bytes,
                "reason": f"team {team} has no quota registered"}
    used = usage.get(team, {"bytes": 0})["bytes"]
    quota = quotas[team]
    after = used + new_bytes
    if after > quota:
        return {"allowed": False, "team": team, "used_bytes": used,
                "quota_bytes": quota, "after_bytes": after,
                "reason": f"write of {new_bytes} bytes would exceed quota "
                          f"({after} > {quota})"}
    return {"allowed": True, "team": team, "used_bytes": used,
            "quota_bytes": quota, "after_bytes": after,
            "reason": "within quota"}


def stale_objects(objects: list[dict], retention_days: int,
                  now: datetime | None = None) -> list[dict]:
    """Objects whose last read is older than the retention window.

    Each object needs "last_read_at" (ISO timestamp) and "kind".
    Checkpoints are never returned here: a checkpoint is kept while its
    run is restorable, and its lifecycle is decided by the checkpoint
    tiering policy, not by read age.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    return [obj for obj in objects
            if obj["kind"] != "checkpoint"
            and _parse(obj["last_read_at"]) < cutoff]


def forecast_full_days(used_bytes: int, capacity_bytes: int,
                       growth_bytes_per_day: int) -> float | None:
    """Days until the pool is full at the current growth rate.

    Returns None when growth is zero or negative (the pool is not
    filling), and 0.0 when it is already full.
    """
    if capacity_bytes <= 0:
        raise ValueError("capacity_bytes must be > 0")
    if used_bytes >= capacity_bytes:
        return 0.0
    if growth_bytes_per_day <= 0:
        return None
    return round((capacity_bytes - used_bytes) / growth_bytes_per_day, 1)


def cleanup_plan(objects: list[dict], retention_days: int,
                 quotas: dict, now: datetime | None = None) -> dict:
    """Plan stale-data cleanup, largest team overage first.

    Returns {"to_delete": [...], "freed_bytes": int, "by_team": {...}}
    where by_team maps each team to the bytes its stale objects free.
    Deleting stale data is the first remedy when a team is over quota;
    nothing is deleted here, only planned.
    """
    stale = stale_objects(objects, retention_days, now)
    by_team: dict[str, int] = {}
    freed = 0
    for obj in stale:
        by_team[obj["team"]] = by_team.get(obj["team"], 0) + obj["size_bytes"]
        freed += obj["size_bytes"]
    usage = attribute_usage(objects)
    over = {team: usage[team]["bytes"] - quotas[team]
            for team in usage if team in quotas
            and usage[team]["bytes"] > quotas[team]}
    order = sorted(stale,
                   key=lambda o: over.get(o["team"], 0),
                   reverse=True)
    return {"to_delete": order, "freed_bytes": freed, "by_team": by_team}
