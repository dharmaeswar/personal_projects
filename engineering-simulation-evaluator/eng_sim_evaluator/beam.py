"""Cantilever beam simulation (Euler-Bernoulli, rectangular section).

Analytic ground truth used by the benchmark:
  deflection at position x under tip load P:
      delta(x) = P * x^2 * (3L - x) / (6 * E * I)
  tip deflection:  P * L^3 / (3 * E * I)
  max bending stress (at the wall):  sigma = P * L * c / I, c = h / 2
  second moment of area:  I = b * h^3 / 12
  mass: rho * b * h * L
All inputs SI units. Pure standard library.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Beam:
    length: float      # L, metres
    width: float       # b, metres
    height: float      # h, metres
    youngs_modulus: float  # E, Pa
    density: float = 7850.0  # rho, kg/m^3 (steel default)

    def __post_init__(self) -> None:
        for name, value in (
            ("length", self.length),
            ("width", self.width),
            ("height", self.height),
            ("youngs_modulus", self.youngs_modulus),
            ("density", self.density),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")

    @property
    def moment_of_inertia(self) -> float:
        return self.width * self.height ** 3 / 12.0

    @property
    def mass(self) -> float:
        return self.density * self.width * self.height * self.length


def deflection(beam: Beam, load: float, x: float) -> float:
    """Deflection (m) at position x from the wall under tip load P (N)."""
    if not 0.0 <= x <= beam.length:
        raise ValueError(f"x must be in [0, {beam.length}], got {x}")
    if load < 0:
        raise ValueError("load must be non-negative")
    return load * x ** 2 * (3 * beam.length - x) / (6 * beam.youngs_modulus * beam.moment_of_inertia)


def tip_deflection(beam: Beam, load: float) -> float:
    return deflection(beam, load, beam.length)


def max_stress(beam: Beam, load: float) -> float:
    """Max bending stress (Pa) at the wall under tip load P."""
    if load < 0:
        raise ValueError("load must be non-negative")
    c = beam.height / 2.0
    return load * beam.length * c / beam.moment_of_inertia


def first_natural_frequency(beam: Beam) -> float:
    """First bending natural frequency (Hz), cantilever approximation.

    f1 = (1.875^2 / 2*pi) * sqrt(E*I / (rho*A*L^4))
    """
    area = beam.width * beam.height
    return (1.875 ** 2 / (2 * math.pi)) * math.sqrt(
        beam.youngs_modulus * beam.moment_of_inertia
        / (beam.density * area * beam.length ** 4)
    )


def deflection_profile(beam: Beam, load: float, n_points: int = 11) -> list[tuple[float, float]]:
    """(x, deflection) pairs from wall to tip."""
    if n_points < 2:
        raise ValueError("n_points must be at least 2")
    return [
        (i * beam.length / (n_points - 1), deflection(beam, load, i * beam.length / (n_points - 1)))
        for i in range(n_points)
    ]
