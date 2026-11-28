"""Decisions: iterate, pivot, or kill — from real usage, not opinion.

A prototype earns its next step from its feedback metrics. The rules
are deliberately plain so a team can argue about the thresholds instead
of about vibes:

- fewer than MIN_FEEDBACK responses: NOT ENOUGH DATA — keep testing.
- avg rating >= SCALE_AT and promoter share >= PROMOTER_AT: ITERATE —
  users like it; keep building on the same idea.
- avg rating <= KILL_AT with enough responses: KILL — users do not
  want it; retire the prototype and free the team.
- anything in between: PIVOT — the problem is real but the current
  shape is wrong; change one thing and re-test.
"""

from __future__ import annotations

MIN_FEEDBACK = 10
SCALE_AT = 4.0
PROMOTER_AT = 0.6
KILL_AT = 2.5


def decide(metrics):
    """Return (decision, reason) for one prototype's metrics dict (or None)."""
    if metrics is None:
        return ("not_enough_data", "no feedback yet — keep testing with real users")
    count = metrics["count"]
    if count < MIN_FEEDBACK:
        return ("not_enough_data",
                f"only {count} feedback responses (need {MIN_FEEDBACK}) — keep testing")
    avg = metrics["avg_rating"]
    promoters = metrics["promoter_share"]
    if avg >= SCALE_AT and promoters >= PROMOTER_AT:
        return ("iterate",
                f"avg rating {avg} with {promoters:.0%} promoters — users like it, keep building")
    if avg <= KILL_AT:
        return ("kill",
                f"avg rating {avg} across {count} responses — users do not want this shape, retire it")
    return ("pivot",
            f"avg rating {avg} is middling — the problem is real but the shape is wrong, change one thing and re-test")
