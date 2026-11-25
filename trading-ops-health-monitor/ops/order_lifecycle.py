"""Order lifecycle checks (synthetic inputs only).

Flags stuck orders (no update within a threshold), unacknowledged
orders, and reject-rate breaches, summarised by symbol. No real
order system is contacted.
"""

STUCK_SECONDS = 30
MAX_REJECT_RATE = 0.05


def check_orders(orders, now_s):
    """Check a list of order dicts.

    Each order: ``order_id``, ``symbol``, ``status`` (new/acked/
    filled/rejected/cancelled), ``last_update_s`` (epoch seconds).
    Returns a dict with stuck orders, unacked orders, reject rate
    and a per-symbol exception count.
    """
    stuck = [
        o for o in orders
        if o["status"] in ("new", "acked") and now_s - o["last_update_s"] > STUCK_SECONDS
    ]
    unacked = [o for o in orders if o["status"] == "new"]
    total = len(orders) or 1
    rejects = [o for o in orders if o["status"] == "rejected"]
    reject_rate = len(rejects) / total
    by_symbol = {}
    for o in stuck + unacked + rejects:
        by_symbol[o["symbol"]] = by_symbol.get(o["symbol"], 0) + 1
    return {
        "stuck": [o["order_id"] for o in stuck],
        "unacked": [o["order_id"] for o in unacked],
        "reject_rate": round(reject_rate, 4),
        "reject_breach": reject_rate > MAX_REJECT_RATE,
        "exceptions_by_symbol": by_symbol,
    }
