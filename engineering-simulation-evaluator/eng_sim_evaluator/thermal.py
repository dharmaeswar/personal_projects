"""Steady-state 1D heat conduction (Fourier's law), pure standard library.

Single wall:  T(x) = T_hot - (T_hot - T_cold) * x / L
              heat flux q = k * (T_hot - T_cold) / L
Composite wall (layers in series): total resistance R = sum(L_i / k_i),
              q = (T_hot - T_cold) / R, interface temperatures from partial sums.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WallLayer:
    thickness: float      # m
    conductivity: float   # W/(m K)

    def __post_init__(self) -> None:
        if self.thickness <= 0 or self.conductivity <= 0:
            raise ValueError("thickness and conductivity must be positive")


def temperature_profile(t_hot: float, t_cold: float, length: float, x: float) -> float:
    if length <= 0:
        raise ValueError("length must be positive")
    if not 0.0 <= x <= length:
        raise ValueError(f"x must be in [0, {length}], got {x}")
    return t_hot - (t_hot - t_cold) * x / length


def heat_flux(t_hot: float, t_cold: float, length: float, conductivity: float) -> float:
    if length <= 0 or conductivity <= 0:
        raise ValueError("length and conductivity must be positive")
    return conductivity * (t_hot - t_cold) / length


def composite_heat_flux(t_hot: float, t_cold: float, layers: list[WallLayer]) -> float:
    if not layers:
        raise ValueError("at least one layer is required")
    resistance = sum(layer.thickness / layer.conductivity for layer in layers)
    return (t_hot - t_cold) / resistance


def composite_interface_temperatures(
    t_hot: float, t_cold: float, layers: list[WallLayer]
) -> list[float]:
    """Temperatures at each layer interface, starting with the hot face.

    Returns len(layers) + 1 values: hot face, each interface, cold face.
    """
    q = composite_heat_flux(t_hot, t_cold, layers)
    temps = [t_hot]
    current = t_hot
    for layer in layers:
        current -= q * layer.thickness / layer.conductivity
        temps.append(current)
    return temps
