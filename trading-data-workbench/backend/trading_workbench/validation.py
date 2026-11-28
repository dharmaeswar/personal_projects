"""Validation rules for market data and order payloads.

These are the same checks a data-quality reviewer runs on a trading feed:
prices must be positive, bid must not cross ask, spreads must stay sane,
timestamps must be ordered with no gaps or future stamps, and orders must
reference a known instrument with a valid side, quantity, and price.
"""

from datetime import datetime, timezone

MAX_SPREAD_BPS = 200  # 2% of mid — wider than any seeded quote spread
MAX_GAP_HOURS = 2


def _parse_ts(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None


def validate_quote(row, now=None):
    """Return a list of issue strings for one quote row (empty = clean)."""
    now = now or datetime.now(timezone.utc)
    issues = []
    for field in ("bid", "ask", "last"):
        value = row.get(field)
        if value is None or not isinstance(value, (int, float)) or value <= 0:
            issues.append(f"{field} must be a positive number, got {value!r}")
    ts = _parse_ts(row.get("ts"))
    if ts is None:
        issues.append(f"ts is not a valid ISO timestamp: {row.get('ts')!r}")
    elif ts > now:
        issues.append(f"ts {row.get('ts')} is in the future")
    bid, ask, last = row.get("bid"), row.get("ask"), row.get("last")
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
        if bid > ask:
            issues.append(f"bid {bid} crosses ask {ask}")
        mid = (bid + ask) / 2
        if mid > 0 and (ask - bid) / mid * 10000 > MAX_SPREAD_BPS:
            issues.append(
                f"spread {(ask - bid) / mid * 10000:.1f} bps exceeds"
                f" {MAX_SPREAD_BPS} bps"
            )
    if isinstance(last, (int, float)) and isinstance(bid, (int, float)) \
            and isinstance(ask, (int, float)):
        if not (bid <= last <= ask):
            issues.append(f"last {last} is outside bid/ask {bid}/{ask}")
    volume = row.get("volume")
    if volume is not None and (not isinstance(volume, int) or volume < 0):
        issues.append(f"volume must be a non-negative integer, got {volume!r}")
    return issues


def check_quote_series(rows):
    """Series-level checks: ordering, duplicates, gaps. Returns issues."""
    issues = []
    seen = set()
    prev = None
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if row.get("ts") in seen:
            issues.append(f"duplicate timestamp {row.get('ts')}")
        seen.add(row.get("ts"))
        if ts is None:
            continue
        if prev is not None and ts <= prev[0]:
            issues.append(f"timestamps out of order at {row.get('ts')}")
        if prev is not None and (ts - prev[0]).total_seconds() > MAX_GAP_HOURS * 3600:
            issues.append(
                f"gap of {(ts - prev[0]).total_seconds() / 3600:.1f}h before"
                f" {row.get('ts')} exceeds {MAX_GAP_HOURS}h"
            )
        prev = (ts, row)
    return issues


def validate_order_payload(payload, store):
    """Return (errors, cleaned) for a POST /api/orders body."""
    errors = []
    if not isinstance(payload, dict):
        return ["request body must be a JSON object"], None
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        errors.append("symbol is required")
    elif store.get_instrument(symbol.strip()) is None:
        errors.append(f"unknown symbol: {symbol}")
    side = payload.get("side")
    if side not in ("BUY", "SELL"):
        errors.append("side must be BUY or SELL")
    qty = payload.get("qty")
    if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
        errors.append("qty must be a positive integer")
    order_type = payload.get("order_type", "MARKET")
    if order_type not in ("MARKET", "LIMIT"):
        errors.append("order_type must be MARKET or LIMIT")
    limit_price = payload.get("limit_price")
    if order_type == "LIMIT":
        if not isinstance(limit_price, (int, float)) or isinstance(limit_price, bool) \
                or limit_price <= 0:
            errors.append("limit_price must be a positive number for LIMIT orders")
    elif limit_price is not None:
        errors.append("limit_price is only allowed for LIMIT orders")
    if errors:
        return errors, None
    return [], {
        "symbol": symbol.strip().upper(),
        "side": side,
        "qty": qty,
        "order_type": order_type,
        "limit_price": limit_price,
    }
