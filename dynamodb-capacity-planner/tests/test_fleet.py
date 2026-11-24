from capplanner import fleet


def _regions(partitions=1):
    return {
        "us-east-1": {"partitions": partitions, "avg_item_kb": 2.0,
                      "storage_gb": 40.0},
    }


def test_event_ready_when_capacity_covers_demand():
    reports = fleet.simulate_event(_regions(2), {"us-east-1": [500.0] * 24})
    r = reports["us-east-1"]
    assert r["throttled_hours"] == 0
    assert r["ready_before_peak"]
    assert fleet.event_readiness(reports)


def test_scaling_action_before_peak():
    # Demand breaches 1 partition (3,000 RCU) mid-series; the peak is a
    # single later hour, so there is time to scale before it arrives.
    series = [500.0] * 12 + [4000.0] * 11 + [5000.0]
    reports = fleet.simulate_event(_regions(1), {"us-east-1": series})
    r = reports["us-east-1"]
    assert len(r["scaling_actions"]) >= 1
    assert r["final_partitions"] >= 2
    assert r["throttled_hours"] == 0


def test_throttled_when_breach_at_peak():
    # Breach only at the final (peak) hour: no time to scale.
    series = [500.0] * 23 + [9000.0]
    reports = fleet.simulate_event(_regions(1), {"us-east-1": series})
    r = reports["us-east-1"]
    assert r["throttled_hours"] == 1
    assert not r["ready_before_peak"]
    assert not fleet.event_readiness(reports)


def test_empty_series_is_ready():
    reports = fleet.simulate_event(_regions(1), {"us-east-1": []})
    assert reports["us-east-1"]["throttled_hours"] == 0
    assert fleet.event_readiness(reports)
