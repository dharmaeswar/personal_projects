"""Service orchestration: enrich -> reconcile -> positions -> P&L -> store.

One run ingests a day's executions and clearing records, enriches the
trades, reconciles them intraday, builds positions and P&L from the
reconciled trades only, persists the result, and returns a plain-dict
report the middle office can read without touching the code.
"""

from . import store
from .enrichment import REFERENCE_DATA, enrich_all
from .models import ClearingRecord, Execution
from .pnl import compute_pnl, total_pnl
from .positions import build_positions
from .reconciliation import reconcile


def run_post_trade(executions, clearing_records, marks, db_path=None):
    """Run one intraday post-trade cycle and return the report dict."""
    enriched = enrich_all(executions)
    result = reconcile(executions, clearing_records, REFERENCE_DATA)
    matched_ids = {m.execution.exec_id for m in result.matches}
    matched_trades = [t for t in enriched if t.execution.exec_id in matched_ids]
    positions = build_positions(matched_trades)
    pnl_rows = compute_pnl(matched_trades, marks)
    realised, unrealised, total = total_pnl(pnl_rows)

    conn = store.connect(db_path)
    store.save_run(conn, enriched, result, positions, pnl_rows)
    stored_positions = store.load_positions(conn)
    stored_breaks = store.load_breaks(conn)
    conn.close()

    return {
        "executions": len(executions),
        "clearing_records": len(clearing_records),
        "matched": result.matched_count,
        "breaks": result.break_count,
        "breaks_by_type": {
            b: sum(1 for x in result.breaks if x.break_type == b)
            for b in sorted({x.break_type for x in result.breaks})
        },
        "unmatched_executions": [
            b.execution.exec_id for b in result.breaks if b.execution
        ],
        "positions": [
            {
                "account": p.account,
                "symbol": p.symbol,
                "net_quantity": p.net_quantity,
                "average_cost": p.average_cost,
            }
            for p in positions
        ],
        "pnl": [
            {
                "account": r.account,
                "symbol": r.symbol,
                "realised": r.realised,
                "unrealised": r.unrealised,
            }
            for r in pnl_rows
        ],
        "realised_pnl": realised,
        "unrealised_pnl": unrealised,
        "total_pnl": total,
        "stored_positions": len(stored_positions),
        "stored_breaks": len(stored_breaks),
    }
