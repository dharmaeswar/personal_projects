"""Use-case intake: score and rank enterprise AI opportunities.

A mid-market deployment starts with use-case selection, not code. Each
candidate use case is scored on business value, data readiness and risk,
then ranked so the team prototypes the highest-value, lowest-risk case
first and defers the rest.
"""

from dataclasses import dataclass, field


@dataclass
class UseCase:
    """One candidate AI use case from a customer workshop."""

    name: str
    domain: str
    description: str
    # Each 0-10, scored in the discovery workshop with the customer.
    value: float  # measurable business outcome (hours saved, errors cut)
    data_readiness: float  # clean, accessible, governed data available
    risk: float  # safety, privacy, regulatory or change-management risk
    stakeholders: list = field(default_factory=list)


def score_use_case(case: UseCase) -> dict:
    """Score a use case. Returns the weighted score (0-10) and a tier.

    Tier: "scale" (ready to productionise), "pilot" (prototype first),
    "defer" (not yet worth the risk). Value and data readiness pull the
    score up; risk pulls it down.
    """
    for label, v in (("value", case.value),
                     ("data_readiness", case.data_readiness),
                     ("risk", case.risk)):
        if not 0 <= v <= 10:
            raise ValueError(f"{label} must be 0-10, got {v}")
    score = 0.45 * case.value + 0.35 * case.data_readiness - 0.20 * case.risk
    score = round(max(0.0, min(10.0, score)), 2)
    if score >= 7.0:
        tier = "scale"
    elif score >= 4.5:
        tier = "pilot"
    else:
        tier = "defer"
    return {"score": score, "tier": tier}


def rank_use_cases(cases: list) -> list:
    """Rank use cases best-first by score, with data readiness as tiebreak."""
    scored = [(case, score_use_case(case)) for case in cases]
    scored.sort(key=lambda pair: (pair[1]["score"], pair[0].data_readiness),
                reverse=True)
    return [{"use_case": case, **result} for case, result in scored]
