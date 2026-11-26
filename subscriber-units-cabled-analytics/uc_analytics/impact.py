"""Bulk-master event impact analysis.

For each bulk activation, de-bulk, or disconnection, compares the
community's average daily Units Cabled in a window before the event
with the window after it, and checks the observed change against the
event's stated unit count. A large unexplained gap means the event did
not land as recorded — or something else moved at the same time.
"""

from datetime import timedelta


def community_daily(actual_rows, community):
    """Sorted [(date, units)] for one community."""
    totals = {}
    for day, _r, c, units in actual_rows:
        if c == community:
            totals[day] = totals.get(day, 0) + units
    return sorted(totals.items())


def event_impact(actual_rows, event, window_days=14):
    """Before/after impact of one bulk event.

    Returns the mean daily units in the ``window_days`` before and
    after the event date, the observed daily change, the expected daily
    change (event units spread over the after window is NOT assumed —
    the event is a step change, so expected daily change equals the
    event's unit count), and the unexplained residual.
    """
    series = dict(community_daily(actual_rows, event["community"]))
    day = event["date"]
    before = [series[d] for d in
              [day - timedelta(days=i) for i in range(window_days, 0, -1)]
              if d in series]
    after = [series[d] for d in
             [day + timedelta(days=i) for i in range(window_days)]
             if d in series]
    if not before or not after:
        return {"event_id": event["event_id"], "community": event["community"],
                "type": event["type"], "date": day.isoformat(),
                "before_mean": None, "after_mean": None,
                "observed_change": None, "expected_change": event["units"],
                "unexplained": None}
    before_mean = sum(before) / len(before)
    after_mean = sum(after) / len(after)
    observed = after_mean - before_mean
    return {"event_id": event["event_id"], "community": event["community"],
            "type": event["type"], "date": day.isoformat(),
            "before_mean": round(before_mean, 1),
            "after_mean": round(after_mean, 1),
            "observed_change": round(observed, 1),
            "expected_change": event["units"],
            "unexplained": round(observed - event["units"], 1)}
