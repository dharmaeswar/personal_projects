"""Deterministic synthetic data for Units Cabled analytics.

Models the three operational feeds the role reconciles plus the forecast
snapshots and bulk-master events:

- ``salesforce``: community-level UC counts as reported in Salesforce.
- ``deployment``: deployment-tracker UC counts (what was actually cabled).
- ``billing``: billing-system UC counts (what is being billed).
- ``actuals``: the agreed daily UC actuals per region (ground truth here).
- ``forecasts``: rolling 120-day forecast snapshots, one per week.
- ``bulk_events``: bulk master activations, de-bulks, disconnections.

A few deliberate discrepancies are seeded so reconciliation has real
breaks to find: a billing feed that drops one community, a deployment
tracker that double-counts one day, and a Salesforce feed that lags a
bulk activation by two days. Everything is reproducible from ``SEED``.
"""

import random
from datetime import date, timedelta

SEED = 42

REGIONS = ("Philadelphia", "Dacula", "Englewood")
COMMUNITIES = {
    "Philadelphia": ["PHL-101", "PHL-102", "PHL-103", "PHL-104"],
    "Dacula": ["DAC-201", "DAC-202", "DAC-203"],
    "Englewood": ["ENG-301", "ENG-302", "ENG-303", "ENG-304"],
}
BASE_UNITS = {
    "PHL-101": 820, "PHL-102": 640, "PHL-103": 455, "PHL-104": 390,
    "DAC-201": 710, "DAC-202": 520, "DAC-203": 305,
    "ENG-301": 690, "ENG-302": 575, "ENG-303": 430, "ENG-304": 260,
}
START = date(2026, 5, 25)  # 180 days ending 2026-11-20
N_DAYS = 180
FORECAST_HORIZON_DAYS = 120


def _event_effect(community, day):
    """Cumulative Units Cabled effect of bulk events up to ``day``."""
    effect = 0
    for event in BULK_EVENTS:
        if event["community"] == community and day >= event["date"]:
            effect += event["units"]
    return effect


def _daily_units(rng, community, day_index):
    """Daily UC count: slow growth, weekly seasonality, small noise."""
    base = BASE_UNITS[community]
    trend = base * 0.0009 * day_index
    dow = (START + timedelta(days=day_index)).weekday()
    seasonal = base * 0.02 if dow in (1, 2) else -base * 0.01 if dow == 6 else 0.0
    noise = rng.uniform(-0.015, 0.015) * base
    day = START + timedelta(days=day_index)
    return max(0, int(round(base + trend + seasonal + noise
                            + _event_effect(community, day))))


def generate(seed=SEED):
    """Return a dict of synthetic feeds. Deterministic for a given seed."""
    rng = random.Random(seed)
    actuals = []      # (date, region, community, units)
    salesforce = []   # (date, region, community, units)
    deployment = []   # (date, region, community, units)
    billing = []      # (date, region, community, units)
    for day_index in range(N_DAYS):
        day = START + timedelta(days=day_index)
        for region, communities in COMMUNITIES.items():
            for community in communities:
                units = _daily_units(rng, community, day_index)
                actuals.append((day, region, community, units))
                # Salesforce lags the PHL-102 bulk activation by 2 days.
                sf_units = units
                if community == "PHL-102" and date(2026, 9, 14) <= day <= date(2026, 9, 15):
                    sf_units = units - 118
                salesforce.append((day, region, community, sf_units))
                # Deployment tracker double-counts ENG-303 on one day.
                dep_units = units + 210 if (community == "ENG-303"
                                             and day == date(2026, 10, 5)) else units
                deployment.append((day, region, community, dep_units))
                # Billing feed drops DAC-203 entirely for one week.
                if community == "DAC-203" and date(2026, 8, 3) <= day <= date(2026, 8, 9):
                    continue
                billing.append((day, region, community, units))

    forecasts = []  # (snapshot_date, target_date, region, forecast_units)
    for week in range(12):
        snap = START + timedelta(days=7 * week)
        for region in REGIONS:
            region_actual = sum(u for d, r, c, u in actuals
                                if r == region and d <= snap)
            days_seen = (snap - START).days + 1
            daily_avg = region_actual / days_seen
            for h in range(1, FORECAST_HORIZON_DAYS + 1):
                target = snap + timedelta(days=h)
                growth = 1.0 + 0.0009 * h
                noise = rng.uniform(-0.02, 0.02)
                forecasts.append((snap, target, region,
                                  int(round(daily_avg * growth * (1 + noise)))))

    bulk_events = BULK_EVENTS
    return {
        "actuals": actuals,
        "salesforce": salesforce,
        "deployment": deployment,
        "billing": billing,
        "forecasts": forecasts,
        "bulk_events": bulk_events,
    }


# Bulk events, defined once so the seeded actuals and the event list agree.
BULK_EVENTS = [
    {"event_id": "BULK-001", "date": date(2026, 9, 14), "community": "PHL-102",
     "type": "activation", "units": 118, "note": "Bulk master activation"},
    {"event_id": "BULK-002", "date": date(2026, 10, 12), "community": "DAC-201",
     "type": "de-bulk", "units": -64, "note": "Bulk master de-bulk"},
    {"event_id": "BULK-003", "date": date(2026, 11, 2), "community": "ENG-301",
     "type": "disconnection", "units": -92, "note": "Bulk disconnection"},
    {"event_id": "BULK-004", "date": date(2026, 8, 24), "community": "PHL-104",
     "type": "activation", "units": 57, "note": "Bulk master activation"},
]
