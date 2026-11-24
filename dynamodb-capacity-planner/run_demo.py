"""End-to-end demo: forecast demand, plan capacity, enforce a quota,
and simulate a fleet event. All data is synthetic."""

from capplanner import capacity, entitlement, fleet, forecast, report


def main():
    rates = forecast.generate_synthetic(24 * 14)
    model = forecast.fit(rates)
    rows = forecast.forecast(model, 24)
    pk = forecast.peak(rows)
    print(report.forecast_report(model, rows[:6], pk))
    print()

    plan = capacity.plan(pk["peak_point"] * 0.7, pk["peak_point"] * 0.3,
                         avg_item_kb=2.0, storage_gb=40.0)
    print(report.capacity_report(plan))
    print()

    ledger = entitlement.QuotaLedger()
    ledger.set_quota(entitlement.Quota("customer-a", 100.0, 50.0))
    now = 0.0
    admitted = throttled = 0
    for _ in range(500):
        status, _ = ledger.admit_request("customer-a", now=now)
        if status == "admitted":
            admitted += 1
        else:
            throttled += 1
        now += 1.0 / 150.0
    print(f"quota demo: admitted {admitted}, throttled {throttled} of 500")
    approved, reason = ledger.request_limit_increase("customer-a", 200.0, 500.0)
    print(f"limit increase: {'approved' if approved else 'denied'} ({reason})")
    print()

    regions = {
        "us-east-1": {"partitions": 2, "avg_item_kb": 2.0, "storage_gb": 40.0},
        "us-west-2": {"partitions": 2, "avg_item_kb": 2.0, "storage_gb": 40.0},
    }
    forecasts = {}
    for region in regions:
        frows = forecast.forecast(model, 24)
        forecasts[region] = [r["forecast"] * (2.0 if r["hour"] >= 24 * 6
                                              else 1.0) for r in frows]
    reports = fleet.simulate_event(regions, forecasts)
    print(report.fleet_report(reports))
    print(f"event ready: {fleet.event_readiness(reports)}")


if __name__ == "__main__":
    main()
