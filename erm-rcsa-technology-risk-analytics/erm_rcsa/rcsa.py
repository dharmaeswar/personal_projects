"""RCSA scoring: inherent risk, control design, Test of Effectiveness,
residual risk, and effective challenge notes.
"""

from __future__ import annotations

DESIGN_EFFECTIVENESS = {
    "Effective": 0.70,
    "Needs Improvement": 0.40,
    "Ineffective": 0.10,
}


def validate_rating(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise ValueError(f"{name} must be an integer 1-5, got {value!r}")
    return value


def inherent_score(risk):
    """Inherent risk = likelihood x impact, on a 1-25 scale."""
    validate_rating(risk.likelihood, "likelihood")
    validate_rating(risk.impact, "impact")
    return risk.likelihood * risk.impact


def risk_band(score):
    if score >= 16:
        return "High"
    if score >= 9:
        return "Medium"
    return "Low"


def toe_pass_rate(control):
    """Test of Effectiveness pass rate from the sampled population."""
    if control.sample_size <= 0:
        raise ValueError("sample_size must be positive")
    if not 0 <= control.exceptions <= control.sample_size:
        raise ValueError("exceptions must be between 0 and sample_size")
    return (control.sample_size - control.exceptions) / control.sample_size


def control_rating(control):
    """A control is Effective only with a sound design AND a ToE pass rate >= 90%."""
    rate = toe_pass_rate(control)
    if control.design == "Effective" and rate >= 0.90:
        return "Effective"
    if control.design == "Ineffective" or rate < 0.75:
        return "Ineffective"
    return "Needs Improvement"


def residual_score(risk, controls_for_risk):
    """Residual risk = inherent x (1 - best control effectiveness).

    Control effectiveness comes from the design rating of the strongest
    control on the risk, reduced when its ToE pass rate is below 90%.
    """
    inherent = inherent_score(risk)
    if not controls_for_risk:
        return float(inherent)
    best = 0.0
    for c in controls_for_risk:
        eff = DESIGN_EFFECTIVENESS[c.design]
        if toe_pass_rate(c) < 0.90:
            eff *= 0.5
        best = max(best, eff)
    return round(inherent * (1 - best), 2)


def rcsa_assessment(risks, controls):
    """Full RCSA table: one row per risk with scores, bands, and challenge notes."""
    by_risk = {}
    for c in controls:
        by_risk.setdefault(c.risk_id, []).append(c)
    rows = []
    for r in risks:
        cs = by_risk.get(r.risk_id, [])
        inherent = inherent_score(r)
        residual = residual_score(r, cs)
        ratings = [control_rating(c) for c in cs]
        if not cs:
            challenge = "CHALLENGE: no control mapped to this risk — control gap, add a control or accept in writing."
        elif "Ineffective" in ratings:
            challenge = "CHALLENGE: at least one control is Ineffective — remediation plan required before sign-off."
        elif residual >= 12:
            challenge = "CHALLENGE: residual risk stays High after controls — escalate to the risk committee."
        else:
            challenge = "No challenge: controls cover the risk within appetite."
        rows.append({
            "risk_id": r.risk_id,
            "name": r.name,
            "category": r.category,
            "source": r.source,
            "inherent": inherent,
            "inherent_band": risk_band(inherent),
            "residual": residual,
            "residual_band": risk_band(int(round(residual))),
            "controls": len(cs),
            "control_ratings": "; ".join(ratings) if ratings else "none",
            "challenge": challenge,
        })
    return rows


def controls_testing_summary(controls):
    """Design vs effectiveness counts for the controls-testing section."""
    out = {"total": len(controls), "effective": 0, "needs_improvement": 0, "ineffective": 0,
           "failing": []}
    for c in controls:
        rating = control_rating(c)
        if rating == "Effective":
            out["effective"] += 1
        elif rating == "Needs Improvement":
            out["needs_improvement"] += 1
        else:
            out["ineffective"] += 1
            out["failing"].append(c.control_id)
    return out
