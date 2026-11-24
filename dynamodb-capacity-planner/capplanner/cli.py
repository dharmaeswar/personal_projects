"""Command-line interface for the DynamoDB Capacity Planner."""

import argparse
import json
import sys

from . import capacity, entitlement, fleet, forecast, report


def _cmd_forecast(args):
    rates = forecast.generate_synthetic(args.hours, base=args.base,
                                        daily_growth=args.growth,
                                        seed=args.seed)
    model = forecast.fit(rates)
    rows = forecast.forecast(model, args.ahead)
    pk = forecast.peak(rows)
    print(report.forecast_report(model, rows, pk))
    if args.json:
        print(report.to_json({"model": model, "forecast": rows, "peak": pk}))
    return 0


def _cmd_plan(args):
    plan = capacity.plan(args.reads, args.writes, args.item_kb,
                         args.storage_gb, headroom=args.headroom)
    print(report.capacity_report(plan))
    if args.json:
        print(report.to_json(plan))
    return 0


def _cmd_enforce(args):
    ledger = entitlement.QuotaLedger()
    ledger.set_quota(entitlement.Quota(args.customer, args.max_rps,
                                       args.max_storage_gb))
    now = 0.0
    admitted = throttled = 0
    for i in range(args.requests):
        status, _ = ledger.admit_request(args.customer, now=now)
        if status == "admitted":
            admitted += 1
        else:
            throttled += 1
        now += 1.0 / args.request_rate
    print(f"customer {args.customer}: admitted {admitted}, "
          f"throttled {throttled} of {args.requests} requests")
    approved, reason = ledger.request_limit_increase(
        args.customer, args.increase_to, args.fleet_free_rps)
    print(f"limit increase to {args.increase_to} rps: "
          f"{'approved' if approved else 'denied'} ({reason})")
    return 0


def _cmd_simulate(args):
    regions = {
        "us-east-1": {"partitions": args.partitions, "avg_item_kb": 2.0,
                      "storage_gb": 40.0},
        "us-west-2": {"partitions": args.partitions, "avg_item_kb": 2.0,
                      "storage_gb": 40.0},
    }
    forecasts = {}
    for region in regions:
        rates = forecast.generate_synthetic(24 * 7, base=args.base,
                                            daily_growth=args.growth,
                                            seed=args.seed)
        model = forecast.fit(rates)
        rows = forecast.forecast(model, 24)
        # Event spike: double the forecast on the last day.
        forecasts[region] = [r["forecast"] * (2.0 if r["hour"] >= 24 * 6
                                              else 1.0) for r in rows]
    reports = fleet.simulate_event(regions, forecasts)
    print(report.fleet_report(reports))
    print(f"event ready: {fleet.event_readiness(reports)}")
    if args.json:
        print(report.to_json(reports))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="capplanner",
        description="Demand forecasting and capacity planning for a "
                    "distributed NoSQL table.")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("forecast", help="forecast hourly request rates")
    f.add_argument("--hours", type=int, default=24 * 14)
    f.add_argument("--base", type=float, default=1000.0)
    f.add_argument("--growth", type=float, default=8.0)
    f.add_argument("--seed", type=int, default=42)
    f.add_argument("--ahead", type=int, default=24)
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=_cmd_forecast)

    pl = sub.add_parser("plan", help="plan partitions for a forecast peak")
    pl.add_argument("--reads", type=float, required=True)
    pl.add_argument("--writes", type=float, required=True)
    pl.add_argument("--item-kb", type=float, default=2.0)
    pl.add_argument("--storage-gb", type=float, default=40.0)
    pl.add_argument("--headroom", type=float, default=0.25)
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=_cmd_plan)

    e = sub.add_parser("enforce", help="simulate quota enforcement")
    e.add_argument("--customer", default="customer-a")
    e.add_argument("--max-rps", type=float, default=100.0)
    e.add_argument("--max-storage-gb", type=float, default=50.0)
    e.add_argument("--requests", type=int, default=500)
    e.add_argument("--request-rate", type=float, default=150.0)
    e.add_argument("--increase-to", type=float, default=200.0)
    e.add_argument("--fleet-free-rps", type=float, default=500.0)
    e.set_defaults(func=_cmd_enforce)

    s = sub.add_parser("simulate", help="simulate a fleet demand event")
    s.add_argument("--partitions", type=int, default=2)
    s.add_argument("--base", type=float, default=1000.0)
    s.add_argument("--growth", type=float, default=8.0)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_simulate)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
