"""Deterministic severity scoring for streaming event signals.

Score is 0-100 from four inputs, all supplied by the caller:
- source reliability (0.0-1.0)
- keyword severity (0.0-1.0): how severe the matched keywords are
- corroborations: how many independent sources reported the same event
- age_seconds: how old the signal is (recency decay)

Bands: >= 70 critical alert, >= 40 watch, below 40 logged only.
"""

from __future__ import annotations

import math

CRITICAL_THRESHOLD = 70.0
WATCH_THRESHOLD = 40.0


def score_event(
    reliability: float,
    keyword_severity: float,
    corroborations: int,
    age_seconds: float,
) -> float:
    """Return a severity score in [0, 100]."""
    if not 0.0 <= reliability <= 1.0:
        raise ValueError("reliability must be in [0, 1]")
    if not 0.0 <= keyword_severity <= 1.0:
        raise ValueError("keyword_severity must be in [0, 1]")
    if corroborations < 0:
        raise ValueError("corroborations must be >= 0")
    if age_seconds < 0:
        raise ValueError("age_seconds must be >= 0")
    base = 55.0 * reliability + 35.0 * keyword_severity
    corroboration_bonus = 10.0 * (1.0 - math.exp(-max(corroborations, 0) / 2.0))
    decay = math.exp(-age_seconds / 3600.0)  # one-hour half-life scale
    score = (base + corroboration_bonus) * decay
    return round(min(max(score, 0.0), 100.0), 2)


def band(score: float) -> str:
    """Severity band for a score: critical, watch, or info."""
    if score >= CRITICAL_THRESHOLD:
        return "critical"
    if score >= WATCH_THRESHOLD:
        return "watch"
    return "info"
