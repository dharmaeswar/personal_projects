"""Clearing margin, stress testing and backtesting.

A small, dependency-free module for the core of a clearing house's
quantitative risk work: how much margin a portfolio of cleared derivatives
needs, how it behaves under stress scenarios, and whether the margin held
would have covered realised losses (backtesting).

Conventions
-----------
* Returns are simple returns (fractions, e.g. -0.02 is a 2% fall).
* Losses are positive numbers: loss = -return. VaR and expected shortfall
  are reported as positive loss amounts at a confidence level.
* Historical VaR is an order statistic, not an interpolated quantile, so
  every value below is exactly reproducible from the sorted loss sample:
  the VaR at confidence ``c`` over ``n`` losses is the ``ceil(c*n)``-th
  smallest loss (1-based). Expected shortfall is the mean of all losses
  at or above the VaR.
* A stress scenario is a dict ``{underlying: shock}`` where a shock is a
  fractional move in the underlying (e.g. -0.05 is a 5% fall). A position
  carries a dollar delta: the P&L for a +100% move in its underlying, so
  P&L under a shock is ``delta * shock``. This is a first-order (delta)
  approximation; gamma and cross-gamma terms are out of scope and the
  limitation is stated in the README.
* All data in the demo and tests is synthetic and seeded. Nothing here
  describes a real clearing member, real portfolio, or real OCC margin
  number.
"""

import math
from statistics import NormalDist

__all__ = [
    "historical_var",
    "historical_expected_shortfall",
    "parametric_var",
    "cornish_fisher_var",
    "portfolio_losses",
    "stress_pnl",
    "worst_stress_loss",
    "margin_requirement",
    "backtest_breaches",
    "kupiec_pof_lr",
    "kupiec_pof_pvalue",
    "margin_report",
]

_NORMAL = NormalDist()


def _sorted_losses(losses):
    losses = [float(x) for x in losses]
    if not losses:
        raise ValueError("losses must not be empty")
    return sorted(losses)


def _check_confidence(confidence):
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")


def historical_var(losses, confidence=0.99):
    """Historical-simulation VaR as a positive loss amount.

    Order statistic: the ``ceil(confidence * n)``-th smallest loss.
    """
    _check_confidence(confidence)
    ordered = _sorted_losses(losses)
    n = len(ordered)
    index = math.ceil(confidence * n) - 1
    return ordered[max(0, min(index, n - 1))]


def historical_expected_shortfall(losses, confidence=0.99):
    """Historical expected shortfall: mean loss at or above the VaR."""
    var = historical_var(losses, confidence)
    tail = [x for x in losses if x >= var]
    return sum(tail) / len(tail)


def parametric_var(mean, std, confidence=0.99):
    """Normal parametric VaR: ``mean + z * std`` as a loss amount.

    ``mean`` and ``std`` are the mean and standard deviation of losses
    (positive-loss convention), so the result is a positive loss.
    """
    _check_confidence(confidence)
    if std < 0:
        raise ValueError("std must not be negative")
    return mean + _NORMAL.inv_cdf(confidence) * std


def cornish_fisher_var(mean, std, skew, excess_kurtosis, confidence=0.99):
    """Cornish-Fisher VaR: normal quantile adjusted for skew and fat tails.

    ``skew`` is the Fisher skewness and ``excess_kurtosis`` is kurtosis
    minus 3. With both zero this reduces exactly to ``parametric_var``.
    Fat tails (positive excess kurtosis) raise the VaR at high confidence.
    """
    _check_confidence(confidence)
    if std < 0:
        raise ValueError("std must not be negative")
    z = _NORMAL.inv_cdf(confidence)
    z_cf = (
        z
        + (z * z - 1.0) * skew / 6.0
        + (z ** 3 - 3.0 * z) * excess_kurtosis / 24.0
        - (2.0 * z ** 3 - 5.0 * z) * skew * skew / 36.0
    )
    return mean + z_cf * std


def portfolio_losses(returns_matrix, weights):
    """Portfolio losses from per-asset scenario returns.

    ``returns_matrix`` is a list of scenarios; each scenario is a list of
    per-asset simple returns in the same order as ``weights``. Returns a
    list of portfolio losses (positive numbers) in scenario order.
    """
    if not returns_matrix:
        raise ValueError("returns_matrix must not be empty")
    if any(len(row) != len(weights) for row in returns_matrix):
        raise ValueError("every scenario must have one return per weight")
    losses = []
    for row in returns_matrix:
        pnl = sum(w * r for w, r in zip(weights, row))
        losses.append(-pnl)
    return losses


def stress_pnl(positions, shocks):
    """First-order (delta) portfolio P&L under one stress scenario.

    ``positions`` is a list of ``{"underlying": str, "delta": float}``
    dicts; ``delta`` is the dollar P&L for a +100% move in the
    underlying. ``shocks`` maps underlying names to fractional shocks.
    Underlyings missing from ``shocks`` are treated as unshocked (0).
    """
    total = 0.0
    for pos in positions:
        shock = shocks.get(pos["underlying"], 0.0)
        total += pos["delta"] * shock
    return total


def worst_stress_loss(positions, scenarios):
    """Worst loss across stress scenarios.

    Returns ``(worst_loss, worst_index)`` where ``worst_loss`` is the
    largest loss (``-P&L``) across the scenarios and ``worst_index`` is
    the index of the scenario that produced it. A scenario that makes
    money contributes a negative loss and never wins.
    """
    if not scenarios:
        raise ValueError("scenarios must not be empty")
    worst_loss = None
    worst_index = None
    for i, shocks in enumerate(scenarios):
        loss = -stress_pnl(positions, shocks)
        if worst_loss is None or loss > worst_loss:
            worst_loss = loss
            worst_index = i
    return worst_loss, worst_index


def margin_requirement(var, stress_loss, floor=0.0):
    """Margin held: the largest of VaR, worst stress loss, and the floor."""
    return max(var, stress_loss, floor)


def backtest_breaches(losses, var_series):
    """Count days where the realised loss exceeded the VaR held that day.

    ``losses`` and ``var_series`` must have the same length. Returns the
    breach count (an integer).
    """
    if len(losses) != len(var_series):
        raise ValueError("losses and var_series must have the same length")
    return sum(1 for loss, var in zip(losses, var_series) if loss > var)


def kupiec_pof_lr(breaches, n, p):
    """Kupiec proportion-of-failures likelihood-ratio statistic.

    Tests whether the observed breach rate ``breaches / n`` is consistent
    with the VaR exception probability ``p`` (e.g. 0.01 for 99% VaR).
    The statistic is chi-squared with 1 degree of freedom under the null.
    Edge cases: zero breaches and breaches on every day are handled by
    the closed-form limit instead of dividing by zero.
    """
    if not 0 <= breaches <= n:
        raise ValueError("breaches must be between 0 and n")
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    if breaches == 0:
        return -2.0 * n * math.log(1.0 - p)
    if breaches == n:
        return -2.0 * n * math.log(p)
    x = breaches
    null_loglik = (n - x) * math.log(1.0 - p) + x * math.log(p)
    alt_rate = x / n
    alt_loglik = (n - x) * math.log(1.0 - alt_rate) + x * math.log(alt_rate)
    return -2.0 * (null_loglik - alt_loglik)


def kupiec_pof_pvalue(breaches, n, p):
    """Two-sided p-value for the Kupiec POF test (chi-squared, 1 dof)."""
    lr = kupiec_pof_lr(breaches, n, p)
    return 1.0 - math.erf(math.sqrt(lr / 2.0))


def margin_report(losses, positions, scenarios, confidence=0.99, floor=0.0):
    """One-call summary: VaR, expected shortfall, stress loss, margin.

    ``losses`` is the historical loss sample for the portfolio,
    ``positions`` and ``scenarios`` feed the stress leg. Returns a dict
    with the VaR, expected shortfall, worst stress loss and its scenario
    index, and the margin requirement (max of VaR, stress loss, floor).
    """
    var = historical_var(losses, confidence)
    es = historical_expected_shortfall(losses, confidence)
    stress_loss, worst_index = worst_stress_loss(positions, scenarios)
    return {
        "confidence": confidence,
        "var": var,
        "expected_shortfall": es,
        "worst_stress_loss": stress_loss,
        "worst_scenario": worst_index,
        "margin": margin_requirement(var, stress_loss, floor),
    }
