"""Fleet-event simulation.

Simulates a multi-region fleet through a demand event (for example a Prime
Day-style traffic spike): each region has provisioned capacity and an hourly
forecast, and the simulator checks whether capacity is in place ahead of
demand, emits scaling actions when the forecast outruns provisioned capacity,
and reports throttled hours if scaling cannot keep up.
"""

from . import capacity as cap


def simulate_event(regions, forecast_by_region, scale_lead_hours=6,
                   scale_step_partitions=1):
    """Simulate one demand event across regions.

    ``regions``: {region: {"partitions": int, "avg_item_kb": float,
    "storage_gb": float}}.
    ``forecast_by_region``: {region: [hourly forecast reads/sec]}.
    Returns a per-region report: hours throttled, scaling actions taken,
    and whether capacity was ready before the peak hour.
    """
    reports = {}
    for region, cfg in regions.items():
        series = forecast_by_region.get(region, [])
        partitions = cfg["partitions"]
        actions = []
        throttled_hours = 0
        peak_hour = None
        ready_before_peak = True
        if series:
            peak_hour = max(range(len(series)), key=lambda h: series[h])
        for hour, rps in enumerate(series):
            provisioned = partitions * cap.RCU_PER_PARTITION
            need = cap._rcu_for(rps, cfg["avg_item_kb"])
            if need > provisioned:
                # Scale up if the breach is far enough ahead to act.
                if peak_hour is not None and hour < peak_hour:
                    partitions += scale_step_partitions
                    actions.append({
                        "hour": hour,
                        "action": "add_partition",
                        "partitions_after": partitions,
                        "reason": f"forecast {rps:.0f} rps exceeds "
                                  f"provisioned {provisioned} RCU",
                    })
                    provisioned = partitions * cap.RCU_PER_PARTITION
                    if cap._rcu_for(rps, cfg["avg_item_kb"]) > provisioned:
                        throttled_hours += 1
                        ready_before_peak = False
                else:
                    throttled_hours += 1
                    ready_before_peak = False
        reports[region] = {
            "final_partitions": partitions,
            "scaling_actions": actions,
            "throttled_hours": throttled_hours,
            "peak_hour": peak_hour,
            "ready_before_peak": ready_before_peak,
        }
    return reports


def event_readiness(reports):
    """True when every region was ready before its peak with no throttling."""
    return all(r["throttled_hours"] == 0 and r["ready_before_peak"]
               for r in reports.values())
