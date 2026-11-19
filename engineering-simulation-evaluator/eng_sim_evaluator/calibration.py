"""Calibration: recover a simulator parameter from synthetic lab measurements.

A beam's Young's modulus E is unknown; we have noisy deflection measurements
taken at known positions under a known load. A grid search over E minimises
the sum of squared residuals between the analytic model and the measurements.
The measurements are synthetic (seeded RNG), labelled as such in the README.
"""

from __future__ import annotations

import random

from .beam import Beam, deflection


def synthetic_measurements(
    beam: Beam, load: float, positions: list[float], noise_std: float, seed: int = 7
) -> list[tuple[float, float]]:
    """(x, measured deflection) pairs with seeded Gaussian noise added."""
    rng = random.Random(seed)
    out = []
    for x in positions:
        true = deflection(beam, load, x)
        out.append((x, true + rng.gauss(0.0, noise_std)))
    return out


def calibrate_youngs_modulus(
    template: Beam,
    load: float,
    measurements: list[tuple[float, float]],
    candidates: list[float],
) -> tuple[float, float]:
    """Best-fit E from `candidates` and its sum of squared residuals.

    `template` supplies every beam property except E; each candidate E is
    substituted in turn and the model is scored against the measurements.
    """
    if not measurements:
        raise ValueError("measurements must be non-empty")
    if not candidates:
        raise ValueError("candidates must be non-empty")
    best_e, best_sse = None, float("inf")
    for e in candidates:
        trial = Beam(
            length=template.length,
            width=template.width,
            height=template.height,
            youngs_modulus=e,
            density=template.density,
        )
        sse = sum((deflection(trial, load, x) - y) ** 2 for x, y in measurements)
        if sse < best_sse:
            best_e, best_sse = e, sse
    assert best_e is not None
    return best_e, best_sse


def calibration_error_pct(recovered_e: float, true_e: float) -> float:
    if true_e <= 0:
        raise ValueError("true_e must be positive")
    return abs(recovered_e - true_e) / true_e * 100.0
