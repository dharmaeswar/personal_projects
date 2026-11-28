"""I/O telemetry and access analytics for training-data workloads.

Records every data access a training job makes — reads, writes,
checkpoint saves and restores — then answers the questions that drive
placement and fixes: which data is hot and which is cold, where metadata
pressure is building, and which operations stall. A stall is an access
whose latency is far above the tier's expected latency, the signal for
a full file system, a runaway metadata load, or a lost checkpoint path.
All data is synthetic demo data.
"""

STALL_MULTIPLIER = 5.0
METADATA_PRESSURE_THRESHOLD = 1000


def record_event(events: list[dict], kind: str, name: str, tier: str,
                 size_bytes: int, latency_ms: float,
                 metadata_ops: int = 0) -> dict:
    """Append one I/O event. Returns the event dict."""
    if kind not in ("read", "write", "checkpoint_save", "checkpoint_restore"):
        raise ValueError(f"unknown event kind: {kind}")
    if latency_ms < 0 or size_bytes < 0 or metadata_ops < 0:
        raise ValueError("latency_ms, size_bytes and metadata_ops must be >= 0")
    event = {"kind": kind, "name": name, "tier": tier,
             "size_bytes": size_bytes, "latency_ms": latency_ms,
             "metadata_ops": metadata_ops}
    events.append(event)
    return event


def hot_cold(events: list[dict], hot_threshold: int = 10) -> dict:
    """Split names into hot (>= threshold reads) and cold (< threshold)."""
    reads: dict[str, int] = {}
    for ev in events:
        if ev["kind"] == "read":
            reads[ev["name"]] = reads.get(ev["name"], 0) + 1
    hot = sorted(n for n, c in reads.items() if c >= hot_threshold)
    cold = sorted(n for n, c in reads.items() if c < hot_threshold)
    return {"hot": hot, "cold": cold, "read_counts": reads}


def find_stalls(events: list[dict], expected_latency_ms: dict) -> list[dict]:
    """Events whose latency is >= STALL_MULTIPLIER x the tier expectation."""
    stalls = []
    for ev in events:
        expected = expected_latency_ms.get(ev["tier"])
        if expected is None:
            continue
        if ev["latency_ms"] >= STALL_MULTIPLIER * expected:
            stalls.append({**ev, "expected_ms": expected,
                           "slowdown": round(ev["latency_ms"] / expected, 1)})
    stalls.sort(key=lambda s: s["slowdown"], reverse=True)
    return stalls


def metadata_pressure(events: list[dict]) -> dict:
    """Total metadata ops per tier and whether any tier is under pressure."""
    per_tier: dict[str, int] = {}
    for ev in events:
        per_tier[ev["tier"]] = per_tier.get(ev["tier"], 0) + ev["metadata_ops"]
    pressured = sorted(t for t, n in per_tier.items()
                       if n >= METADATA_PRESSURE_THRESHOLD)
    return {"per_tier": per_tier, "pressured_tiers": pressured,
            "threshold": METADATA_PRESSURE_THRESHOLD}


def placement_suggestions(events: list[dict]) -> list[str]:
    """Plain-language placement fixes derived from the telemetry.

    Hot data sitting on a slow tier should move up; cold data on the
    fastest tier should move down; checkpoint restores that stall need
    a local-first copy.
    """
    counts = hot_cold(events)["read_counts"]
    suggestions = []
    slow_tiers = {"OBJECT", "ARCHIVE"}
    for ev in events:
        if ev["kind"] == "read" and ev["tier"] in slow_tiers \
                and counts.get(ev["name"], 0) >= 10:
            suggestions.append(
                f"Move {ev['name']} from {ev['tier']} to a faster tier: "
                f"{counts[ev['name']]} reads")
        if ev["kind"] == "read" and ev["tier"] == "NVME" \
                and counts.get(ev["name"], 0) < 2:
            suggestions.append(
                f"Move {ev['name']} off NVME to a cheaper tier: "
                f"only {counts[ev['name']]} read(s)")
        if ev["kind"] == "checkpoint_restore" and ev["latency_ms"] >= 5000:
            suggestions.append(
                f"Keep a local-first copy of {ev['name']}: restore took "
                f"{ev['latency_ms']} ms")
    seen = set()
    unique = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def summary(events: list[dict], expected_latency_ms: dict) -> dict:
    """One-page roll-up: totals, hot/cold split, stalls, metadata pressure."""
    total_bytes = sum(ev["size_bytes"] for ev in events)
    total_latency = sum(ev["latency_ms"] for ev in events)
    kinds: dict[str, int] = {}
    for ev in events:
        kinds[ev["kind"]] = kinds.get(ev["kind"], 0) + 1
    return {"events": len(events), "by_kind": kinds,
            "total_bytes": total_bytes,
            "total_latency_ms": round(total_latency, 1),
            "hot_cold": hot_cold(events),
            "stalls": find_stalls(events, expected_latency_ms),
            "metadata": metadata_pressure(events),
            "suggestions": placement_suggestions(events)}
