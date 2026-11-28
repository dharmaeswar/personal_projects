"""Fund multiples: DPI, RVPI and TVPI in exact decimal arithmetic.

Multiples answer a different question from a rate of return: how many
times the paid-in capital has come back (DPI), is still held as
residual value (RVPI), or the two combined (TVPI). They are the
standard private-capital multiples and, unlike an IRR, they are pure
ratios of money sums — no solver is involved, so they are exact.

Conventions (same as perf/pme.py):
- A flow is (day, amount): positive for a contribution into the fund
  (paid-in), negative for a distribution out. Days are in years from
  the first flow. All amounts are ``decimal.Decimal``; floats are
  rejected by ``money()``.
- residual_nav is the value still held in the fund at the
  measurement date, as a non-negative Decimal amount.
- paid_in is the sum of contributions. DPI = distributions /
  paid_in, RVPI = residual_nav / paid_in, TVPI = (distributions +
  residual_nav) / paid_in, so TVPI == DPI + RVPI exactly; the
  conformance harness pins that identity as an invariant.
"""

from decimal import Decimal

from .decimal_solver import money, canonical_sum


def _split(flows):
    """Validate flows and split into (paid_in, distributions)."""
    flows = [(money(day), money(amount)) for day, amount in flows]
    if not flows:
        raise ValueError("no cash flows")
    if min(day for day, _ in flows) != 0:
        raise ValueError("first cash flow must be at day 0")
    paid_in = canonical_sum(
        [(day, amount) for day, amount in flows if amount > 0])
    distributions = -canonical_sum(
        [(day, amount) for day, amount in flows if amount < 0])
    if paid_in == 0:
        raise ValueError("multiples need at least one contribution")
    return paid_in, distributions


def paid_in_total(flows):
    """Total contributions (paid-in capital) as a Decimal."""
    paid_in, _ = _split(flows)
    return paid_in


def distributions_total(flows):
    """Total distributions as a positive Decimal."""
    _, distributions = _split(flows)
    return distributions


def dpi(flows):
    """Distributions to paid-in: money returned per unit contributed."""
    paid_in, distributions = _split(flows)
    return distributions / paid_in


def rvpi(flows, residual_nav):
    """Residual value to paid-in: value still held per unit contributed."""
    paid_in, _ = _split(flows)
    residual_nav = money(residual_nav)
    if residual_nav < 0:
        raise ValueError("residual NAV must not be negative")
    return residual_nav / paid_in


def tvpi(flows, residual_nav):
    """Total value to paid-in: (distributions + residual NAV) / paid-in."""
    paid_in, distributions = _split(flows)
    residual_nav = money(residual_nav)
    if residual_nav < 0:
        raise ValueError("residual NAV must not be negative")
    return (distributions + residual_nav) / paid_in
