"""Fairness slices for compliance models.

A compliance model that flags one customer group far more often than
another — at the same underlying risk — is a fair-lending / disparate
impact problem, not just a performance problem. These checks surface it.
"""

import numpy as np


def flag_rates_by_group(frame, scores, threshold=0.5):
    """Alert (flag) rate and SAR capture by customer group."""
    scores = np.asarray(scores)
    flagged = scores >= threshold
    frame = frame.reset_index(drop=True)
    out = {}
    for group, idx in frame.groupby("group").groups.items():
        pos = np.asarray(sorted(idx))
        flagged_g = flagged[pos]
        y_g = frame["sar_worthy"].to_numpy()[pos]
        out[group] = {
            "count": int(len(pos)),
            "flag_rate": float(flagged_g.mean()),
            "capture_rate": float(y_g[flagged_g].sum() / y_g.sum()) if y_g.sum() else 0.0,
            "base_rate": float(y_g.mean()),
        }
    return out


def disparate_impact_ratio(flag_rates):
    """Min / max flag rate across groups (the four-fifths rule uses 0.8)."""
    rates = [v["flag_rate"] for v in flag_rates.values()]
    if not rates or max(rates) == 0:
        return 1.0
    return float(min(rates) / max(rates))


def equal_opportunity_gap(flag_rates):
    """Largest gap in SAR capture rate (true-positive rate) across groups."""
    captures = [v["capture_rate"] for v in flag_rates.values()]
    if not captures:
        return 0.0
    return float(max(captures) - min(captures))
