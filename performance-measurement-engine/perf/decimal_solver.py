"""Exact-decimal arithmetic and a safeguarded bracketing solver.

The index-calculation rules this module exists for:

- No floating-point types for money or IRR solves: every amount, rate
  and index level is a ``decimal.Decimal``. ``money()`` rejects floats
  outright, so a float can never silently enter a calculation.
- Summation uses a canonical flow order (sorted by day, then amount)
  so the same run always adds in the same order.
- The solver brackets before it iterates: it scans for a sign change
  first and refuses to iterate on an unbracketed root. It reports
  convergence diagnostics and flags ill-conditioning — a converged
  result whose NPV slope is tiny, or more than one sign change in the
  scan (multiple roots), is reported as such instead of silently
  returning a number that looks precise but means nothing.
"""

from decimal import Decimal, InvalidOperation

DEFAULT_PRECISION = 28


def money(value):
    """Convert an int, str or Decimal to Decimal. Floats are rejected.

    A float literal such as 0.1 is not exactly 0.1, so accepting one
    would defeat the exact-arithmetic rule this module enforces.
    """
    if isinstance(value, bool):
        raise TypeError("bool is not a money value")
    if isinstance(value, float):
        raise TypeError(
            "float %r is not allowed for money; pass str, int or Decimal"
            % (value,))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ValueError("not a decimal amount: %r" % (value,))
    raise TypeError("unsupported money type: %r" % (type(value).__name__,))


def canonical_sum(flows):
    """Sum (day, amount) flows in canonical order: by day, then amount.

    Amounts must already be Decimal (use money() first). Sorting
    before summing pins the addition order, so replays are identical.
    """
    total = Decimal(0)
    for _, amount in sorted(flows, key=lambda f: (f[0], f[1])):
        total += amount
    return total


def decimal_npv(cash_flows, rate):
    """NPV of (day, amount) Decimal flows discounted at Decimal rate."""
    rate = money(rate)
    total = Decimal(0)
    for day, amount in sorted(cash_flows, key=lambda f: (f[0], f[1])):
        total += amount / (Decimal(1) + rate) ** day
    return total


def _scan_bracket(func, low, high, steps=200):
    """Scan [low, high] for sign changes. Returns (bracket, sign_changes).

    bracket is the first (lo, hi) pair whose values straddle zero, or
    None. sign_changes counts every adjacent pair that straddles zero.
    """
    step = (high - low) / steps
    prev_x = low
    prev_f = func(prev_x)
    if prev_f == 0:
        return (low, low), 0
    changes = 0
    bracket = None
    for i in range(1, steps + 1):
        x = low + step * i
        f = func(x)
        if f == 0:
            return (x, x), changes
        if (f > 0) != (prev_f > 0):
            changes += 1
            if bracket is None:
                bracket = (prev_x, x)
        prev_x, prev_f = x, f
    return bracket, changes


def _polish(func, mid):
    """Snap a converged root to a short decimal when that is exact.

    Bisection lands within tolerance of the root, not on it, so a
    root the methodology states exactly (10%, 21%) would otherwise
    come back as 0.09999999999999999949... The polish rounds the
    result to 15 decimal places and keeps the rounded value ONLY if
    the function is exactly zero there — it verifies exactness, it
    never assumes it. Otherwise the bisection result stands.
    """
    try:
        candidate = mid.quantize(Decimal("1e-15"))
    except InvalidOperation:
        return mid
    if func(candidate) == 0:
        return candidate
    return mid


def solve_root_decimal(func, low, high, tol=Decimal("1e-18"),
                       max_iter=200, steps=200):
    """Safeguarded root solve: bracket first, then bisect.

    func must take and return Decimal. Returns (root, diagnostics)
    where diagnostics holds bracket, iterations, residual, and
    ill_conditioned / multiple_roots flags. Raises ValueError when no
    sign change is found in [low, high].
    """
    low, high = money(low), money(high)
    bracket, changes = _scan_bracket(func, low, high, steps=steps)
    if bracket is None:
        raise ValueError(
            "no sign change in [%s, %s]; root is not bracketed" % (low, high))
    lo, hi = bracket
    flo = func(lo)
    if flo == 0:
        return lo, {"bracket": (lo, hi), "iterations": 0,
                    "residual": Decimal(0), "ill_conditioned": False,
                    "multiple_roots": changes > 1}
    for iteration in range(1, max_iter + 1):
        mid = (lo + hi) / 2
        fmid = func(mid)
        if fmid == 0 or (hi - lo) / 2 < tol:
            root = _polish(func, mid)
            return root, {"bracket": bracket, "iterations": iteration,
                          "residual": abs(func(root)),
                          "ill_conditioned": False,
                          "multiple_roots": changes > 1}
        if (fmid > 0) == (flo > 0):
            lo, flo = mid, fmid
        else:
            hi = mid
    return (lo + hi) / 2, {"bracket": bracket, "iterations": max_iter,
                            "residual": abs(func((lo + hi) / 2)),
                            "ill_conditioned": True,
                            "multiple_roots": changes > 1}


def solve_irr_decimal(cash_flows, low="-0.9999", high="10",
                      tol=Decimal("1e-18"), max_iter=200):
    """Money-weighted return (IRR) solved in exact decimal arithmetic.

    cash_flows is a list of (day, amount) with Decimal days and
    amounts; the first flow must be at day 0. Returns
    (rate, diagnostics). diagnostics["ill_conditioned"] is True when
    the NPV slope at the root is tiny relative to the cash-flow scale
    (a converged number that is still meaningless) or the solver hit
    max_iter, and diagnostics["multiple_roots"] is True when the scan
    found more than one sign change.
    """
    flows = [(money(day), money(amount)) for day, amount in cash_flows]
    if not flows:
        raise ValueError("no cash flows")
    if min(day for day, _ in flows) != 0:
        raise ValueError("first cash flow must be at day 0")

    def npv(rate):
        return decimal_npv(flows, rate)

    rate, diag = solve_root_decimal(npv, low, high, tol=tol,
                                    max_iter=max_iter)
    # Ill-conditioning check: NPV slope at the root, by central
    # difference, against the scale of the flows. A flat NPV means a
    # small residual error moves the root a long way.
    scale = max(abs(amount) for _, amount in flows)
    h = Decimal("1e-9")
    slope = abs((npv(rate + h) - npv(rate - h)) / (2 * h))
    if scale > 0 and slope < Decimal("1e-6") * scale:
        diag["ill_conditioned"] = True
    return rate, diag
