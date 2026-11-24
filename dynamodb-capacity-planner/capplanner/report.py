"""Text and JSON reports for forecasts, capacity plans and fleet events."""

import json


def forecast_report(model, rows, peak_row):
    lines = [
        "Demand forecast",
        f"  fitted on {model['n_points']} hourly observations",
        f"  residual std: {model['residual_std']:.1f} requests/sec",
        f"  peak forecast: {peak_row['peak_point']:.0f} rps "
        f"(upper band {peak_row['peak_upper']:.0f}) at hour {peak_row['hour']}",
        "  hour | forecast | lower | upper",
    ]
    for r in rows:
        lines.append(f"  {r['hour']:>4} | {r['forecast']:>8.0f} | "
                     f"{r['lower']:>6.0f} | {r['upper']:>6.0f}")
    return "\n".join(lines)


def capacity_report(plan):
    return "\n".join([
        "Capacity plan",
        f"  partitions: {plan['partitions']} "
        f"(limiting factor: {plan['limiting_factor']})",
        f"  required: {plan['required_rcu']} RCU, {plan['required_wcu']} WCU",
        f"  provisioned: {plan['provisioned_rcu']} RCU, "
        f"{plan['provisioned_wcu']} WCU",
        f"  headroom: {plan['headroom_fraction'] * 100:.1f}%",
        f"  estimated cost: ${plan['monthly_cost_usd']:.2f}/month",
    ])


def fleet_report(reports):
    lines = ["Fleet event simulation"]
    for region, r in reports.items():
        lines.append(
            f"  {region}: {r['final_partitions']} partitions, "
            f"{len(r['scaling_actions'])} scaling actions, "
            f"{r['throttled_hours']} throttled hours, "
            f"ready before peak: {r['ready_before_peak']}"
        )
    return "\n".join(lines)


def to_json(payload):
    return json.dumps(payload, indent=2, sort_keys=True)
