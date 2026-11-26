"""Cross-source reconciliation for Units Cabled reporting.

Compares the three operational feeds — Salesforce, deployment tracker,
billing — against the agreed actuals on the (date, community) key and
flags every break: a value mismatch beyond tolerance, a row missing
from one feed, or a row present in only one feed. Each break carries a
category so follow-up goes to the right business partner.
"""

from collections import defaultdict

TOLERANCE_UNITS = 5  # breaks smaller than this are rounding noise


def _index(rows):
    return {(day, community): units for day, _region, community, units in rows}


def reconcile(actual_rows, salesforce_rows, deployment_rows, billing_rows,
              tolerance=TOLERANCE_UNITS):
    """Return a list of discrepancy dicts, sorted by (date, community).

    Categories:
    - ``missing_in_billing`` — community/day absent from the billing feed
    - ``missing_in_salesforce`` / ``missing_in_deployment`` — same idea
    - ``salesforce_mismatch`` / ``deployment_mismatch`` /
      ``billing_mismatch`` — feed value differs from actuals by more than
      ``tolerance`` units
    """
    actual = _index(actual_rows)
    feeds = {"salesforce": _index(salesforce_rows),
             "deployment": _index(deployment_rows),
             "billing": _index(billing_rows)}
    breaks = []
    keys = set(actual)
    for name, feed in feeds.items():
        keys |= set(feed)
    for day, community in sorted(keys):
        expected = actual.get((day, community))
        for name, feed in feeds.items():
            value = feed.get((day, community))
            if expected is None:
                breaks.append({"date": day, "community": community,
                               "source": name, "category": f"unexpected_in_{name}",
                               "expected": None, "reported": value,
                               "difference": value})
            elif value is None:
                breaks.append({"date": day, "community": community,
                               "source": name, "category": f"missing_in_{name}",
                               "expected": expected, "reported": None,
                               "difference": -expected})
            elif abs(value - expected) > tolerance:
                breaks.append({"date": day, "community": community,
                               "source": name, "category": f"{name}_mismatch",
                               "expected": expected, "reported": value,
                               "difference": value - expected})
    return breaks


def summarize(breaks):
    """Count breaks by category and by source."""
    by_category = defaultdict(int)
    by_source = defaultdict(int)
    for b in breaks:
        by_category[b["category"]] += 1
        by_source[b["source"]] += 1
    return {"total": len(breaks),
            "by_category": dict(sorted(by_category.items())),
            "by_source": dict(sorted(by_source.items()))}
