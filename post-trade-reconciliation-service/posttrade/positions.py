"""Positions: net quantity and average cost per account / symbol.

Average-cost method: adding to a position blends the cost; reducing a
position keeps the average cost of what remains. Positions are built
only from reconciled trades, so breaks never leak into the book.
"""

from .models import EnrichedTrade, Position


def build_positions(trades: list[EnrichedTrade]) -> list[Position]:
    """Aggregate net positions from reconciled enriched trades."""
    book: dict[tuple, dict] = {}
    for trade in trades:
        exc = trade.execution
        key = (exc.account, exc.symbol)
        signed = exc.quantity if exc.side == "BUY" else -exc.quantity
        mult = trade.instrument.multiplier if trade.instrument else 1
        state = book.setdefault(key, {"net": 0, "cost": 0.0, "mult": mult})
        if state["net"] == 0 or (state["net"] > 0) == (signed > 0):
            total = abs(state["net"]) + abs(signed)
            state["cost"] = (
                state["cost"] * abs(state["net"]) + exc.price * abs(signed)
            ) / total
            state["net"] += signed
        else:
            state["net"] += signed
            if state["net"] == 0:
                state["cost"] = 0.0
    return [
        Position(
            account=account,
            symbol=symbol,
            net_quantity=state["net"],
            average_cost=round(state["cost"], 4),
            multiplier=state["mult"],
        )
        for (account, symbol), state in sorted(book.items())
        if state["net"] != 0
    ]
