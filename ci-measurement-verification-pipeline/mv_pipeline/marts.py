"""Marts layer: the tables operations and partners actually read.

- ``mart_site_event_summary``: one row per site per event — baseline,
  actual, curtailed kW/kWh and payment, plus an over-use flag.
- ``mart_payments``: the payment report — one row per site, the amount
  owed and the traceability fields (event date, intervals counted).
"""

from __future__ import annotations


def mart_site_event_summary(performance, event_date):
    rows = []
    for site in sorted(performance):
        p = performance[site]
        rows.append({
            "site_id": site, "event_date": str(event_date.date()),
            "intervals": p["intervals"],
            "baseline_kw": p["baseline_kw"], "actual_kw": p["actual_kw"],
            "curtailed_kw": p["curtailed_kw"],
            "curtailed_kwh": p["curtailed_kwh"],
            "payment_usd": p["payment_usd"],
            "over_use": p["over_use"],
        })
    return rows


def mart_payments(performance, event_date):
    return [{"site_id": site, "event_date": str(event_date.date()),
             "payment_usd": performance[site]["payment_usd"],
             "curtailed_kwh": performance[site]["curtailed_kwh"],
             "intervals": performance[site]["intervals"]}
            for site in sorted(performance)]
