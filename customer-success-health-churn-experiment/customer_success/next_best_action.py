"""Next best action: one ranked action per customer, from health + propensity.

Actions are the levers a Customer Success team actually has — onboarding help,
training, coverage review, save offers, expansion consults — and each one is
gated on the customer it fits, so a healthy customer never gets a save offer
and an at-risk one never gets an upsell pitch first.
"""
ACTIONS = {
    "onboarding_concierge": "Guided onboarding: concierge setup session to reach first value faster",
    "training_session": "Feature training: 1:1 session on the highest-value unused feature",
    "coverage_review": "Coverage review: CSM check-in on service coverage and open tickets",
    "save_offer": "Save play: retention offer + executive sponsor outreach",
    "expansion_consult": "Expansion consult: seats / plan review against usage headroom",
    "self_serve_nudge": "Self-serve nudge: in-product tip + help-center guide (no human touch)",
}


def next_best_actions(c, churn_p, expand_p):
    """Return [(action, score, reason)] ranked best first for one customer."""
    scored = []
    band = c["health_band"]
    if c["time_to_value_days"] > 30 and c["months_on_platform"] <= 6:
        scored.append(("onboarding_concierge", 0.55 + 0.4 * churn_p,
                       "slow time-to-value in first 6 months"))
    if c["features_adopted"] <= 3:
        scored.append(("training_session", 0.45 + 0.3 * (1 - c["features_adopted"] / 8),
                       "low feature adoption"))
    if band in ("Watch", "At-Risk") and c["tickets_90d"] >= 3:
        scored.append(("coverage_review", 0.5 + 0.4 * churn_p,
                       "elevated tickets with weakening health"))
    if churn_p >= 0.5 or band == "At-Risk":
        scored.append(("save_offer", 0.4 + 0.55 * churn_p,
                       "high churn propensity / at-risk health"))
    if band == "Healthy" and expand_p >= 0.4:
        scored.append(("expansion_consult", 0.4 + 0.5 * expand_p,
                       "healthy with expansion headroom"))
    if not scored:
        scored.append(("self_serve_nudge", 0.3, "healthy, low-touch: self-serve is enough"))
    scored.sort(key=lambda x: -x[1])
    return [(a, round(s, 2), r) for a, s, r in scored]


def rank_actions(scored_customers, churn_probs, expand_probs):
    """Top action per customer for a scored list; returns {customer_id: action}."""
    out = {}
    for c, cp, ep in zip(scored_customers, churn_probs, expand_probs):
        out[c["customer_id"]] = next_best_actions(c, cp, ep)[0]
    return out
