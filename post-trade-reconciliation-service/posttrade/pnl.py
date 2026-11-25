"""P&L: realised P&L on position reductions, unrealised vs mark prices.

Realised P&L uses the same average-cost method as positions.py: when a
trade reduces a position, the P&L on the reduced quantity is
(price - average cost) x quantity x multiplier, signed so a long
position gains when it sells above cost and a short position gains
when it buys back below cost. Unrealised P&L is
(mark - average cost) x net quantity x multiplier per open position.
"""

from .models import EnrichedTrade, Position, SymbolPnl


def compute_pnl(
    trades: list[EnrichedTrade], marks: dict[str, float]
) -> list[SymbolPnl]:
    """Compute realised + unrealised P&L per account / symbol."""
    book: dict[tuple, dict] = {}
    realised: dict[tuple, float] = {}
    for trade in sorted(trades, key=lambda t: t.execution.exec_id):
        exc = trade.execution
        key = (exc.account, exc.symbol)
        mult = trade.instrument.multiplier if trade.instrument else 1
        signed = exc.quantity if exc.side == "BUY" else -exc.quantity
        state = book.setdefault(key, {"net": 0, "cost": 0.0, "mult": mult})
        realised.setdefault(key, 0.0)
        if state["net"] == 0 or (state["net"] > 0) == (signed > 0):
            total = abs(state["net"]) + abs(signed)
            state["cost"] = (
                state["cost"] * abs(state["net"]) + exc.price * abs(signed)
            ) / total
            state["net"] += signed
        else:
            reduce_qty = min(abs(state["net"]), abs(signed))
            sign = 1 if state["net"] > 0 else -1
            realised[key] += (
                (exc.price - state["cost"]) * reduce_qty * mult * sign
            )
            state["net"] += signed
            if state["net"] == 0:
                state["cost"] = 0.0
            elif abs(signed) > reduce_qty:
                # Trade flipped the position: the rest opens a new one.
                state["cost"] = exc.price
    out: list[SymbolPnl] = []
    for key in sorted(book):
        state = book[key]
        mark = marks.get(key[1])
        unrealised = 0.0
        if state["net"] != 0 and mark is not None:
            unrealised = (mark - state["cost"]) * state["net"] * state["mult"]
        out.append(
            SymbolPnl(
                account=key[0],
                symbol=key[1],
                realised=round(realised.get(key, 0.0), 2),
                unrealised=round(unrealised, 2),
                net_quantity=state["net"],
            )
        )
    return out


def total_pnl(rows: list[SymbolPnl]) -> tuple[float, float, float]:
    """Return (realised, unrealised, total) across all P&L rows."""
    realised = round(sum(r.realised for r in rows), 2)
    unrealised = round(sum(r.unrealised for r in rows), 2)
    return realised, unrealised, round(realised + unrealised, 2)


def positions_from_book(trades: list[EnrichedTrade]) -> list[Position]:
    """Positions derived from the same average-cost walk as compute_pnl."""
    from .positions import build_positions

    return build_positions(trades)
