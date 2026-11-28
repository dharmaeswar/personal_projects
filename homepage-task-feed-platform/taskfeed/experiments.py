"""Experiments: deterministic assignment and honest readouts.

Experiments run on the feed itself (e.g. a new ranking variant). Assignment
is a stable hash of (user, experiment) so a user always sees the same arm.
Readouts report completion rate and time-to-action per arm, with a
sample-ratio-mismatch guardrail: if the observed split does not match the
intended split, the readout is flagged untrustworthy instead of shipped.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass


def assign_variant(user_id: str, experiment: str, variants: tuple[str, ...] = ("control", "treatment")) -> str:
    """Deterministic variant for a user; stable across feed builds."""
    digest = hashlib.sha256(f"{experiment}:{user_id}".encode()).hexdigest()
    return variants[int(digest, 16) % len(variants)]


def _z_critical_two_sided(alpha: float = 0.05) -> float:
    # Normal approximation critical values for the common alphas.
    return {0.05: 1.96, 0.01: 2.576, 0.10: 1.645}.get(alpha, 1.96)


def two_proportion_ztest(
    successes_a: int, n_a: int, successes_b: int, n_b: int
) -> tuple[float, float]:
    """Return (z, two-sided p-value) for B vs A completion rates."""
    if n_a == 0 or n_b == 0:
        raise ValueError("both arms need observations")
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    p_pool = (successes_a + successes_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if se == 0:
        return 0.0, 1.0
    z = (p_b - p_a) / se
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return z, p_value


@dataclass
class ExperimentReadout:
    experiment: str
    rate_control: float
    rate_treatment: float
    lift: float  # treatment minus control, in percentage points
    z: float
    p_value: float
    significant: bool
    srm_flagged: bool
    note: str


def readout(
    experiment: str,
    *,
    control_success: int,
    control_n: int,
    treatment_success: int,
    treatment_n: int,
    intended_split: float = 0.5,
    alpha: float = 0.05,
) -> ExperimentReadout:
    """Completion-rate readout with an SRM guardrail on the split.

    SRM check: chi-square on observed vs intended counts; a large deviation
    means assignment broke and the lift cannot be trusted.
    """
    total = control_n + treatment_n
    if total == 0:
        raise ValueError("no observations in either arm")
    expected_treatment = total * intended_split
    expected_control = total * (1 - intended_split)
    chi2 = ((treatment_n - expected_treatment) ** 2 / expected_treatment) + (
        (control_n - expected_control) ** 2 / expected_control
    )
    srm_flagged = chi2 > 3.84  # chi-square, 1 df, alpha 0.05
    z, p_value = two_proportion_ztest(
        control_success, control_n, treatment_success, treatment_n
    )
    rate_c = control_success / control_n if control_n else 0.0
    rate_t = treatment_success / treatment_n if treatment_n else 0.0
    note = ""
    if srm_flagged:
        note = "SRM flagged: observed split does not match the intended split; do not ship on this readout."
    elif p_value < alpha:
        note = "Significant at alpha %.2f; lift is %.1f points." % (alpha, (rate_t - rate_c) * 100)
    else:
        note = "Not significant at alpha %.2f." % alpha
    return ExperimentReadout(
        experiment=experiment,
        rate_control=round(rate_c, 4),
        rate_treatment=round(rate_t, 4),
        lift=round((rate_t - rate_c) * 100, 2),
        z=round(z, 3),
        p_value=round(p_value, 4),
        significant=(p_value < alpha and not srm_flagged),
        srm_flagged=srm_flagged,
        note=note,
    )
