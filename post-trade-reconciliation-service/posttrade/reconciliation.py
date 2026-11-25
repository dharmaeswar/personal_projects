"""Intraday trade reconciliation: executions against clearing records.

Matching is deterministic. Executions and clearing records are paired
on (symbol, side, trade date, account); a pair then has to agree on
quantity, and on price within a tolerance of max(0.05, two ticks).
Anything else becomes a break with a plain-word reason, so the middle
office can work it instead of the run failing.
"""

from dataclasses import dataclass, field

from .models import Break, ClearingRecord, Execution, Instrument, Match

DEFAULT_TOLERANCE = 0.05


@dataclass
class ReconciliationResult:
    matches: list = field(default_factory=list)
    breaks: list = field(default_factory=list)

    @property
    def matched_count(self) -> int:
        return len(self.matches)

    @property
    def break_count(self) -> int:
        return len(self.breaks)


def _tolerance(instrument: Instrument | None) -> float:
    if instrument is None:
        return DEFAULT_TOLERANCE
    return max(DEFAULT_TOLERANCE, 2 * instrument.tick_size)


def _key(record) -> tuple:
    return (record.symbol, record.side, record.trade_date, record.account)


def reconcile(
    executions: list[Execution],
    clearing_records: list[ClearingRecord],
    instruments: dict | None = None,
) -> ReconciliationResult:
    """Reconcile executions to clearing records, in exec-id order."""
    ref = instruments or {}
    by_key: dict[tuple, list[ClearingRecord]] = {}
    for rec in sorted(clearing_records, key=lambda r: r.clearing_id):
        by_key.setdefault(_key(rec), []).append(rec)

    result = ReconciliationResult()
    used: set[str] = set()

    for exc in sorted(executions, key=lambda e: e.exec_id):
        candidates = [c for c in by_key.get(_key(exc), []) if c.clearing_id not in used]
        if not candidates:
            result.breaks.append(
                Break(
                    break_type="MISSING_CLEARING",
                    execution=exc,
                    clearing=None,
                    detail=f"no clearing record for {exc.exec_id}",
                )
            )
            continue
        # Prefer an exact quantity + price match, then a quantity match
        # inside price tolerance, then report what actually differs.
        exact = next(
            (c for c in candidates if c.quantity == exc.quantity and c.price == exc.price),
            None,
        )
        if exact is not None:
            used.add(exact.clearing_id)
            result.matches.append(Match(exc, exact, "MATCHED", 0.0))
            continue
        same_qty = next((c for c in candidates if c.quantity == exc.quantity), None)
        if same_qty is not None:
            tol = _tolerance(ref.get(exc.symbol))
            diff = exc.price - same_qty.price
            if abs(diff) <= tol:
                used.add(same_qty.clearing_id)
                result.matches.append(
                    Match(exc, same_qty, "MATCHED_WITH_PRICE_VARIANCE", diff)
                )
            else:
                used.add(same_qty.clearing_id)
                result.breaks.append(
                    Break(
                        break_type="PRICE_BREAK",
                        execution=exc,
                        clearing=same_qty,
                        detail=(
                            f"price {exc.price} vs clearing {same_qty.price} "
                            f"(diff {diff:.2f} exceeds tolerance {tol:.2f})"
                        ),
                    )
                )
            continue
        first = candidates[0]
        used.add(first.clearing_id)
        result.breaks.append(
            Break(
                break_type="QTY_MISMATCH",
                execution=exc,
                clearing=first,
                detail=(
                    f"quantity {exc.quantity} vs clearing {first.quantity} "
                    f"for {exc.exec_id} / {first.clearing_id}"
                ),
            )
        )

    for rec in sorted(clearing_records, key=lambda r: r.clearing_id):
        if rec.clearing_id not in used:
            result.breaks.append(
                Break(
                    break_type="MISSING_EXECUTION",
                    execution=None,
                    clearing=rec,
                    detail=f"no execution for clearing record {rec.clearing_id}",
                )
            )
    return result
