"""Sensitivity analysis: revalue a model under bumped inputs."""
from typing import Callable, Dict, Sequence


def sensitivity_table(price_fn: Callable[[float], float], base_input: float,
                      bumps: Sequence[float] = (-0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02)) -> Dict[float, float]:
    """Return {bump: change in model output vs the base input value}."""
    base_value = price_fn(base_input)
    return {b: price_fn(base_input + b) - base_value for b in bumps}
