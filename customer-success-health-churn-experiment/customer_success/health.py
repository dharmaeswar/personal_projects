"""Customer health scoring: one 0-100 score per customer, plus a band.

Components are the signals a Customer Success team actually manages to:
adoption (are they using the product?), engagement (are they coming back?),
support load (are they stuck?), tenure/payment (are they settled in?) and
advocacy (would they recommend it?). Weights sum to 1.
"""
from .data import FEATURES

WEIGHTS = {
    "adoption": 0.30,
    "engagement": 0.25,
    "support": 0.20,
    "tenure": 0.15,
    "advocacy": 0.10,
}


def health_score(c):
    adoption = c["features_adopted"] / FEATURES
    engagement = min(1.0, c["weekly_logins"] / 25.0)
    support = max(0.0, 1.0 - c["tickets_90d"] / 8.0)
    tenure = min(1.0, c["months_on_platform"] / 24.0)
    advocacy = c["nps"] / 10.0
    score = 100 * (
        WEIGHTS["adoption"] * adoption
        + WEIGHTS["engagement"] * engagement
        + WEIGHTS["support"] * support
        + WEIGHTS["tenure"] * tenure
        + WEIGHTS["advocacy"] * advocacy
    )
    return round(score, 1)


def health_band(score):
    if score >= 70:
        return "Healthy"
    if score >= 50:
        return "Watch"
    return "At-Risk"


def score_all(customers):
    """Attach score + band to each customer dict (copy) and return the list."""
    out = []
    for c in customers:
        row = dict(c)
        row["health_score"] = health_score(c)
        row["health_band"] = health_band(row["health_score"])
        out.append(row)
    return out


def health_mix(scored):
    mix = {"Healthy": 0, "Watch": 0, "At-Risk": 0}
    for c in scored:
        mix[c["health_band"]] += 1
    return mix


def retention_by_band(scored):
    """Observed retention per health band — the check that the score means something."""
    out = {}
    for band in ("Healthy", "Watch", "At-Risk"):
        rows = [c for c in scored if c["health_band"] == band]
        if rows:
            out[band] = round(sum(1 for c in rows if c["retained"]) / len(rows), 3)
    return out
