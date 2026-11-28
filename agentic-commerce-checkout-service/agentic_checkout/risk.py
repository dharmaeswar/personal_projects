"""Fraud and risk signals: a deterministic risk score for each attempt.

Every payment attempt is scored from observable signals only — no model
calls, so the same attempt always scores the same way:

- amount anomaly: the attempt is far above the merchant's typical ticket;
- velocity: many attempts from the same agent in a short window;
- new merchant: the agent has never paid this merchant before;
- blocked merchant: a hard deny, whatever the score.

Scores are 0-100.  Below 40 is ALLOW, 40-69 is REVIEW (hold for a human
or a step-up check), 70+ is DENY.  Every contributing reason is returned
so a reviewer can see exactly why an attempt was held or denied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class Attempt:
    agent_id: str
    merchant_id: str
    amount_cents: int
    currency: str
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class RiskDecision:
    score: int
    decision: str  # ALLOW | REVIEW | DENY
    reasons: tuple


class RiskEngine:
    """Scores attempts against merchant baselines and recent history."""

    def __init__(self, *, merchant_median_cents: dict[str, int],
                 blocked_merchants: frozenset = frozenset(),
                 velocity_window: timedelta = timedelta(minutes=10),
                 velocity_limit: int = 5) -> None:
        self.merchant_median_cents = merchant_median_cents
        self.blocked_merchants = blocked_merchants
        self.velocity_window = velocity_window
        self.velocity_limit = velocity_limit
        self._history: list[Attempt] = []

    def score(self, attempt: Attempt) -> RiskDecision:
        reasons: list[str] = []
        score = 0
        if attempt.merchant_id in self.blocked_merchants:
            return RiskDecision(100, "DENY",
                                (f"merchant {attempt.merchant_id!r} is blocked",))
        median = self.merchant_median_cents.get(attempt.merchant_id)
        if median and attempt.amount_cents > 3 * median:
            score += 40
            reasons.append(
                f"amount {attempt.amount_cents} is over 3x the merchant "
                f"median ticket {median}"
            )
        elif median and attempt.amount_cents > 2 * median:
            score += 20
            reasons.append(
                f"amount {attempt.amount_cents} is over 2x the merchant "
                f"median ticket {median}"
            )
        window_start = attempt.at - self.velocity_window
        recent = [a for a in self._history
                  if a.agent_id == attempt.agent_id and a.at >= window_start]
        if len(recent) >= self.velocity_limit:
            score += 40
            reasons.append(
                f"velocity: {len(recent) + 1} attempts in "
                f"{self.velocity_window} from this agent"
            )
        seen_merchants = {a.merchant_id for a in self._history
                          if a.agent_id == attempt.agent_id}
        if attempt.merchant_id not in seen_merchants and self._history:
            score += 15
            reasons.append(f"first payment by this agent to {attempt.merchant_id!r}")
        self._history.append(attempt)
        score = min(score, 100)
        decision = "ALLOW" if score < 40 else "REVIEW" if score < 70 else "DENY"
        return RiskDecision(score, decision, tuple(reasons))
