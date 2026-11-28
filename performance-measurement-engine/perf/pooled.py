"""Pooled and neutrally weighted money-weighted returns.

A composite of funds needs one IRR, and there are two standard ways
to build it — they answer different questions, so both are exposed
as separate, separately versioned measures:

- Pooled IRR: merge every fund's cash flows into one stream and
  solve once. Large funds dominate, because their flows are larger.
  This is the return of the combined pool of money.
- Neutrally weighted IRR: first scale each fund's flows by a weight
  inversely proportional to its paid-in capital, so every fund
  contributes the same effective amount of money, then merge and
  solve. Each fund counts equally regardless of size. The weights
  are w_i = (1 / paid_in_i) / sum_j(1 / paid_in_j) and sum to 1.

Flows here use the investor perspective of perf/decimal_solver.py:
negative is money paid in, positive is money back, the first flow of
each fund is at day 0. All amounts are Decimal and the solve uses
the safeguarded bracketing solver, so the same ill-conditioning and
multiple-roots diagnostics apply.
"""

from decimal import Decimal

from .decimal_solver import money, canonical_sum, solve_irr_decimal


def _check_funds(funds_flows):
    funds = []
    for flows in funds_flows:
        flows = [(money(day), money(amount)) for day, amount in flows]
        if not flows:
            raise ValueError("a fund has no cash flows")
        if min(day for day, _ in flows) != 0:
            raise ValueError("first cash flow of each fund must be at day 0")
        funds.append(flows)
    if not funds:
        raise ValueError("no funds")
    return funds


def _paid_in(flows):
    """Investor-perspective paid-in: the positive total of money in."""
    return -canonical_sum(
        [(day, amount) for day, amount in flows if amount < 0])


def pooled_irr(funds_flows):
    """IRR of all funds' flows merged into a single stream.

    Returns (rate, diagnostics) from the safeguarded solver.
    """
    funds = _check_funds(funds_flows)
    merged = [flow for flows in funds for flow in flows]
    return solve_irr_decimal(merged)


def neutral_weights(funds_flows):
    """Per-fund neutral weights: inverse paid-in, normalised to sum to 1."""
    funds = _check_funds(funds_flows)
    inverses = []
    for flows in funds:
        paid_in = _paid_in(flows)
        if paid_in == 0:
            raise ValueError("neutral weighting needs paid-in capital")
        inverses.append(Decimal(1) / paid_in)
    total = sum(inverses)
    return [inverse / total for inverse in inverses]


def neutrally_weighted_irr(funds_flows):
    """IRR after scaling each fund's flows by its neutral weight.

    Returns (rate, diagnostics) from the safeguarded solver.
    """
    funds = _check_funds(funds_flows)
    weights = neutral_weights(funds_flows)
    merged = []
    for weight, flows in zip(weights, funds):
        merged.extend((day, amount * weight) for day, amount in flows)
    return solve_irr_decimal(merged)
