"""Capacity planning for a distributed NoSQL table.

Given a forecast peak (reads/writes per second), item size and stored data,
computes how many partitions are needed, what provisioned throughput that
implies, headroom against the forecast, and a rough cost estimate.

Planning assumptions (public DynamoDB limits, used as planning constants,
not as claims about any real table):
  - one partition holds at most 3,000 read capacity units (RCU) and
    1,000 write capacity units (WCU) and 10 GB of data.
  - one RCU = one strongly consistent read per second for an item up to 4 KB;
    one WCU = one write per second for an item up to 1 KB.
"""

import math

RCU_PER_PARTITION = 3000
WCU_PER_PARTITION = 1000
GB_PER_PARTITION = 10.0
RCU_HOUR_COST = 0.00013  # USD per RCU-hour (on-demand-style planning figure)
WCU_HOUR_COST = 0.00065  # USD per WCU-hour
STORAGE_GB_MONTH_COST = 0.25  # USD per GB-month


def _rcu_for(reads_per_sec, avg_item_kb):
    units = math.ceil(avg_item_kb / 4.0)
    return reads_per_sec * units


def _wcu_for(writes_per_sec, avg_item_kb):
    units = math.ceil(avg_item_kb / 1.0)
    return writes_per_sec * units


def plan(peak_reads_per_sec, peak_writes_per_sec, avg_item_kb, storage_gb,
         headroom=0.25):
    """Plan partitions and provisioned capacity for the forecast peak.

    ``headroom`` is the extra fraction of capacity held above the peak so a
    burst does not throttle. Returns a dict with the full plan.
    """
    if peak_reads_per_sec < 0 or peak_writes_per_sec < 0:
        raise ValueError("request rates cannot be negative")
    if avg_item_kb <= 0 or storage_gb < 0:
        raise ValueError("item size must be positive and storage non-negative")
    if not 0 <= headroom < 1:
        raise ValueError("headroom must be in [0, 1)")

    need_rcu = _rcu_for(peak_reads_per_sec, avg_item_kb) / (1 - headroom)
    need_wcu = _wcu_for(peak_writes_per_sec, avg_item_kb) / (1 - headroom)
    by_reads = math.ceil(need_rcu / RCU_PER_PARTITION)
    by_writes = math.ceil(need_wcu / WCU_PER_PARTITION)
    by_storage = math.ceil(storage_gb / GB_PER_PARTITION)
    partitions = max(1, by_reads, by_writes, by_storage)
    provisioned_rcu = partitions * RCU_PER_PARTITION
    provisioned_wcu = partitions * WCU_PER_PARTITION
    actual_headroom = 1 - (_rcu_for(peak_reads_per_sec, avg_item_kb)
                           / provisioned_rcu)
    monthly_cost = (
        provisioned_rcu * RCU_HOUR_COST * 24 * 30
        + provisioned_wcu * WCU_HOUR_COST * 24 * 30
        + storage_gb * STORAGE_GB_MONTH_COST
    )
    return {
        "partitions": partitions,
        "limiting_factor": (
            "reads" if by_reads >= by_writes and by_reads >= by_storage
            else "writes" if by_writes >= by_storage else "storage"
        ),
        "required_rcu": math.ceil(need_rcu),
        "required_wcu": math.ceil(need_wcu),
        "provisioned_rcu": provisioned_rcu,
        "provisioned_wcu": provisioned_wcu,
        "headroom_fraction": round(actual_headroom, 4),
        "monthly_cost_usd": round(monthly_cost, 2),
    }


def check_headroom(plan_result, peak_reads_per_sec, avg_item_kb):
    """True if the plan's provisioned RCU still covers the peak reads."""
    need = _rcu_for(peak_reads_per_sec, avg_item_kb)
    return need <= plan_result["provisioned_rcu"]
