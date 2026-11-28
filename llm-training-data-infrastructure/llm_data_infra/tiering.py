"""Storage tiering for AI training data: placement, caching and movement.

Models the layer the MARS AI Data team builds between storage and the
workload. Four tiers, fastest first:

  NVME     - node-local NVMe, hot data: active training shards, the latest
             checkpoint, streaming-loader working sets.
  SHARED_FS- distributed parallel file system (Lustre / WEKA / VAST /
             GPFS / Ceph class): warm datasets and checkpoints shared
             across many GPU nodes.
  OBJECT   - object storage at scale (S3 or compatible): cold datasets,
             older checkpoints, scratch archives.
  ARCHIVE  - deep archive: retained only for compliance / reproducibility.

Placement is decided from access temperature (reads in the last window),
size, and whether the object is a checkpoint. The latest checkpoint of a
run always stays hot; older checkpoints tier down. Every placement and
move is recorded so a reader can reproduce where any object lives.
All sizes are bytes; all data is synthetic demo data.
"""

TIERS = ("NVME", "SHARED_FS", "OBJECT", "ARCHIVE")

# Relative read latency per tier, in milliseconds, for demo estimates.
TIER_LATENCY_MS = {"NVME": 0.1, "SHARED_FS": 2.0, "OBJECT": 25.0, "ARCHIVE": 900.0}

# Capacity of each tier in the demo model (bytes).
TIER_CAPACITY_BYTES = {
    "NVME": 2 * 1024 ** 4,        # 2 TiB of node-local NVMe
    "SHARED_FS": 50 * 1024 ** 4,  # 50 TiB of shared parallel file system
    "OBJECT": 500 * 1024 ** 4,    # 500 TiB of object storage
    "ARCHIVE": 5 * 1024 ** 5,     # 5 PiB of archive
}


def place_object(kind: str, size_bytes: int, reads_last_day: int,
                 is_latest_checkpoint: bool = False) -> str:
    """Choose the tier for one object.

    kind: "dataset", "checkpoint", "scratch" or "snapshot".
    Hot, frequently read objects and the latest checkpoint go to NVMe;
    warm shared data goes to the shared file system; cold or large
    objects go to object storage; snapshots kept only for retention
    go to archive.
    """
    if size_bytes < 0 or reads_last_day < 0:
        raise ValueError("size_bytes and reads_last_day must be >= 0")
    if kind not in ("dataset", "checkpoint", "scratch", "snapshot"):
        raise ValueError(f"unknown object kind: {kind}")
    if kind == "snapshot":
        return "ARCHIVE"
    if is_latest_checkpoint:
        return "NVME"
    if kind == "checkpoint" and reads_last_day >= 5:
        return "SHARED_FS"
    if kind == "checkpoint":
        return "OBJECT"
    if reads_last_day >= 50:
        return "NVME"
    if reads_last_day >= 5:
        return "SHARED_FS"
    if size_bytes >= 10 * 1024 ** 3:  # 10 GiB or larger, rarely read
        return "OBJECT"
    return "SHARED_FS"


def tier_for_checkpoint(step: int, latest_step: int, reads_last_day: int) -> str:
    """Tier for one training checkpoint, given its step and the latest step.

    The newest checkpoint is restored first after a failure, so it stays
    on NVMe; the previous one stays on the shared file system for a fast
    fallback; older checkpoints tier to object storage.
    """
    if step == latest_step:
        return "NVME"
    if step == latest_step - 1:
        return "SHARED_FS"
    return place_object("checkpoint", 0, reads_last_day)


def plan_moves(objects: list[dict]) -> list[dict]:
    """Return the moves needed to bring objects onto their ideal tiers.

    Each object: {"name", "kind", "size_bytes", "reads_last_day",
    "current_tier", "is_latest_checkpoint" (optional)}.
    A move is {"name", "from", "to", "reason"}; objects already placed
    correctly produce no move. Moves are ordered hot-first so the data
    training needs next is moved first.
    """
    moves = []
    for obj in objects:
        if obj["kind"] == "checkpoint" and "step" in obj and "latest_step" in obj:
            ideal = tier_for_checkpoint(obj["step"], obj["latest_step"],
                                        obj["reads_last_day"])
        else:
            ideal = place_object(obj["kind"], obj["size_bytes"],
                                 obj["reads_last_day"],
                                 obj.get("is_latest_checkpoint", False))
        if ideal != obj["current_tier"]:
            reason = (f"reads_last_day={obj['reads_last_day']} "
                      f"size_bytes={obj['size_bytes']} -> {ideal}")
            moves.append({"name": obj["name"], "from": obj["current_tier"],
                          "to": ideal, "reason": reason})
    order = {tier: i for i, tier in enumerate(TIERS)}
    moves.sort(key=lambda m: order[m["to"]])
    return moves


def tier_usage(objects: list[dict]) -> dict:
    """Bytes used and object count per tier for a list of placed objects."""
    usage = {tier: {"bytes": 0, "objects": 0} for tier in TIERS}
    for obj in objects:
        tier = obj["current_tier"]
        if tier not in usage:
            raise ValueError(f"unknown tier: {tier}")
        usage[tier]["bytes"] += obj["size_bytes"]
        usage[tier]["objects"] += 1
    for tier in TIERS:
        cap = TIER_CAPACITY_BYTES[tier]
        usage[tier]["capacity_bytes"] = cap
        usage[tier]["pct_full"] = round(100.0 * usage[tier]["bytes"] / cap, 2)
    return usage


def estimated_read_ms(tier: str, size_bytes: int, throughput_mbps: float = 1000.0) -> float:
    """Rough read time for an object: tier latency plus transfer time."""
    if tier not in TIER_LATENCY_MS:
        raise ValueError(f"unknown tier: {tier}")
    if size_bytes < 0 or throughput_mbps <= 0:
        raise ValueError("size_bytes must be >= 0 and throughput_mbps > 0")
    transfer_ms = (size_bytes / (throughput_mbps * 1024 * 1024)) * 1000.0
    return round(TIER_LATENCY_MS[tier] + transfer_ms, 3)
