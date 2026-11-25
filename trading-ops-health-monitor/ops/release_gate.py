"""Pre-open readiness gate for the trading day (synthetic inputs).

All checks must pass for a go verdict: feeds healthy, no stuck
orders, latency inside SLO, no open sev-1, runbooks current.
"""


def readiness_gate(checks):
    """checks: dict with keys ``feeds_ok``, ``orders_ok``,
    ``latency_ok``, ``no_open_sev1``, ``runbooks_current`` (bools).
    Returns a dict with a go/no-go verdict and the failing checks.
    """
    required = ["feeds_ok", "orders_ok", "latency_ok", "no_open_sev1", "runbooks_current"]
    failing = [name for name in required if not checks.get(name, False)]
    return {
        "verdict": "go" if not failing else "no-go",
        "failing": failing,
        "checks_passed": len(required) - len(failing),
        "checks_total": len(required),
    }
