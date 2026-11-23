"""Finite-difference PDE solvers for the Black-Scholes equation.

Solves dV/dt + 0.5*sigma^2*S^2*d2V/dS2 + r*S*dV/dS - r*V = 0 backwards
from expiry to today, for European calls and puts.

Two schemes:
- ``explicit_price`` — simple explicit stepping; the caller must respect
  the stability limit (dt <= dS^2 / (sigma^2 * S_max^2)), otherwise it
  raises instead of returning garbage.
- ``crank_nicolson_price`` — unconditionally stable; the tridiagonal
  system at each step is solved with the Thomas algorithm.

Pure standard library.
"""

import math


def _payoff(S: float, K: float, option: str) -> float:
    return max(S - K, 0.0) if option == "call" else max(K - S, 0.0)


def _boundary(S_max: float, K: float, t_left: float, r: float, option: str):
    """Boundary values at S=0 and S=S_max with t_left years to expiry."""
    disc = math.exp(-r * t_left)
    if option == "call":
        return 0.0, S_max - K * disc
    return K * disc, 0.0


def _thomas(a, b, c, d):
    """Solve a tridiagonal system (a: sub, b: diag, c: super, d: rhs)."""
    n = len(d)
    cp = [0.0] * n
    dp = [0.0] * n
    cp[0] = c[0] / b[0]
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        denom = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / denom if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / denom
    x = [0.0] * n
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


def _grid(S0: float, K: float, T: float, r: float, sigma: float,
          option: str, n_space: int, n_time: int, s_max_mult: float = 3.0):
    if S0 <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        raise ValueError("S0, K, T, sigma must be positive")
    if option not in ("call", "put"):
        raise ValueError("option must be 'call' or 'put'")
    if n_space < 10 or n_time < 1:
        raise ValueError("need n_space >= 10 and n_time >= 1")
    S_max = s_max_mult * max(S0, K)
    dS = S_max / n_space
    dt = T / n_time
    spot = [j * dS for j in range(n_space + 1)]
    values = [_payoff(s, K, option) for s in spot]
    return S_max, dS, dt, spot, values


def explicit_price(S0: float, K: float, T: float, r: float, sigma: float,
                   option: str = "call", n_space: int = 200,
                   n_time: int = 2000) -> float:
    """Explicit finite-difference price. Raises if the step is unstable."""
    S_max, dS, dt, spot, values = _grid(
        S0, K, T, r, sigma, option, n_space, n_time)
    if dt > dS * dS / (sigma * sigma * S_max * S_max):
        raise ValueError(
            f"explicit scheme unstable: dt={dt:.6f} exceeds the limit "
            f"{dS * dS / (sigma * sigma * S_max * S_max):.6f}; "
            "increase n_time or use crank_nicolson_price")
    for step in range(n_time):
        t_left = T - (step + 1) * dt
        new = values[:]
        lo_b, hi_b = _boundary(S_max, K, t_left, r, option)
        new[0], new[-1] = lo_b, hi_b
        for j in range(1, n_space):
            s = spot[j]
            alpha = 0.5 * sigma * sigma * s * s / (dS * dS)
            beta = r * s / (2 * dS)
            p_up = dt * (alpha + beta)
            p_mid = 1 - dt * r - 2 * dt * alpha
            p_down = dt * (alpha - beta)
            new[j] = (p_down * values[j - 1] + p_mid * values[j]
                      + p_up * values[j + 1])
        values = new
    return _interp(S0, spot, values)


def crank_nicolson_price(S0: float, K: float, T: float, r: float, sigma: float,
                         option: str = "call", n_space: int = 200,
                         n_time: int = 100) -> float:
    """Crank-Nicolson finite-difference price (unconditionally stable)."""
    S_max, dS, dt, spot, values = _grid(
        S0, K, T, r, sigma, option, n_space, n_time)
    m = n_space - 1  # interior points j = 1 .. n_space-1
    for step in range(n_time):
        # Boundaries at the known (later) time level and the unknown
        # (earlier) time level: the RHS uses the known level, the solved
        # values use the earlier level.
        t_old = T - step * dt
        t_left = T - (step + 1) * dt
        lo_old, hi_old = _boundary(S_max, K, t_old, r, option)
        lo_b, hi_b = _boundary(S_max, K, t_left, r, option)
        a, b, c, d = [], [], [], []
        for j in range(1, n_space):
            s = spot[j]
            alpha = 0.5 * sigma * sigma * s * s / (dS * dS)
            beta = r * s / (2 * dS)
            aj = 0.5 * dt * (alpha - beta)
            bj = 1 + dt * alpha + 0.5 * dt * r
            cj = 0.5 * dt * (alpha + beta)
            a.append(-aj)
            b.append(bj)
            c.append(-cj)
            rhs = (aj * values[j - 1] + (2 - bj) * values[j]
                   + cj * values[j + 1])
            if j == 1:
                rhs += aj * lo_old
            if j == n_space - 1:
                rhs += cj * hi_old
            d.append(rhs)
        inner = _thomas(a, b, c, d)
        values = [lo_b] + inner + [hi_b]
    return _interp(S0, spot, values)


def _interp(S0: float, spot, values) -> float:
    """Linear interpolation of the grid value at S0."""
    if S0 <= spot[0]:
        return values[0]
    if S0 >= spot[-1]:
        return values[-1]
    j = 0
    while spot[j + 1] < S0:
        j += 1
    w = (S0 - spot[j]) / (spot[j + 1] - spot[j])
    return values[j] * (1 - w) + values[j + 1] * w
