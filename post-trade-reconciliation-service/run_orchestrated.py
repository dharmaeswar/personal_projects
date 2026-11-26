"""Demo runner: the same seeded post-trade cycle, run as a DAG.

Ingests executions, clearing records, marks and text notes from
three input types (CSV, CSV, free text), then runs enrich ->
reconcile -> positions -> P&L as scheduled jobs on the orchestrator's
worker pool, and writes posttrade_orchestrated_report.json. The seeded
inputs deliberately include dirty rows (one bad execution, one
duplicate execution, one bad mark, one malformed note) so the run
shows quarantine working end to end. All data is synthetic.
"""

import json

from posttrade.ingest import (
    parse_clearing_csv,
    parse_executions_csv,
    parse_marks_csv,
    parse_text_notes,
)
from posttrade.orchestrator import Job, run_dag
from posttrade.service import run_post_trade

EXECUTIONS_CSV = """exec_id,symbol,side,quantity,price,trade_date,venue,account
E1,AAPL 260117C00250000,BUY,10,4.20,2026-11-24,CBOE,ACC-001
E2,AAPL 260117C00250000,SELL,4,4.50,2026-11-24,CBOE,ACC-001
E3,SPX 260117P00590000,BUY,5,12.30,2026-11-24,CBOE,ACC-001
E4,MSFT 260117C00420000,BUY,20,2.10,2026-11-24,NYSE ARCA,ACC-002
E5,AAPL,BUY,100,250.00,2026-11-24,NASDAQ,ACC-001
E6,AAPL 260117C00250000,BUY,6,4.25,2026-11-24,CBOE,ACC-001
E7,SPX 260117P00590000,SELL,2,12.80,2026-11-24,CBOE,ACC-001
E8,XYZ 260117C00010000,BUY,3,1.00,2026-11-24,CBOE,ACC-001
E9,AAPL,HOLD,5,250.00,2026-11-24,NASDAQ,ACC-001
E1,AAPL 260117C00250000,BUY,10,4.20,2026-11-24,CBOE,ACC-001
"""

CLEARING_CSV = """clearing_id,symbol,side,quantity,price,trade_date,account,fees
C1,AAPL 260117C00250000,BUY,10,4.20,2026-11-24,ACC-001,1.50
C2,AAPL 260117C00250000,SELL,4,4.50,2026-11-24,ACC-001,1.20
C3,SPX 260117P00590000,BUY,5,12.30,2026-11-24,ACC-001,2.00
C4,MSFT 260117C00420000,BUY,20,2.10,2026-11-24,ACC-002,0.80
C5,AAPL,BUY,100,250.00,2026-11-24,ACC-001,0.00
C6,AAPL 260117C00250000,BUY,5,4.25,2026-11-24,ACC-001,0.55
C7,MSFT 260117C00420000,SELL,10,2.40,2026-11-24,ACC-002,1.10
"""

MARKS_CSV = """symbol,price
AAPL 260117C00250000,4.60
SPX 260117P00590000,12.00
MSFT 260117C00420000,2.25
AAPL,252.00
XYZ 260117C00010000,not-a-price
"""

NOTES_TEXT = """AAPL 260117C00250000: weekly expiry, watch pin risk into expiry
AAPL: earnings next week, expect higher realised volatility
this line has no colon and is quarantined
SPX 260117P00590000: monthly expiry, wide wings on downside puts
"""


def build_jobs():
    """The post-trade DAG: ingest (parallel) -> reconcile -> P&L -> report."""
    return [
        Job("ingest_executions", lambda ctx: parse_executions_csv(EXECUTIONS_CSV)),
        Job("ingest_clearing", lambda ctx: parse_clearing_csv(CLEARING_CSV)),
        Job("ingest_marks", lambda ctx: parse_marks_csv(MARKS_CSV)),
        Job("ingest_notes", lambda ctx: parse_text_notes(NOTES_TEXT)),
        Job(
            "enrich_reconcile",
            lambda ctx: run_post_trade(
                ctx["ingest_executions"].records,
                ctx["ingest_clearing"].records,
                ctx["ingest_marks"].records,
            ),
            deps=["ingest_executions", "ingest_clearing", "ingest_marks"],
        ),
        Job(
            "report",
            lambda ctx: {
                "post_trade": ctx["enrich_reconcile"],
                "quarantined": {
                    name: [
                        {
                            "source": q.source,
                            "row": q.row_number,
                            "reason": q.reason,
                        }
                        for q in ctx[name].quarantined
                    ]
                    for name in (
                        "ingest_executions",
                        "ingest_clearing",
                        "ingest_marks",
                        "ingest_notes",
                    )
                },
                "notes": ctx["ingest_notes"].records,
            },
            deps=["enrich_reconcile", "ingest_notes"],
        ),
    ]


def main():
    report = run_dag(build_jobs(), max_workers=4)
    summary = report.results["report"].result
    post_trade = summary["post_trade"]
    with open("posttrade_orchestrated_report.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(
        f"DAG: {report.succeeded} succeeded, {report.failed} failed, "
        f"{report.skipped} skipped"
    )
    for name, outcome in report.results.items():
        print(
            f"  {name}: {outcome.status} "
            f"({outcome.attempts} attempt(s), {outcome.duration_seconds:.3f}s)"
        )
    print(
        f"Executions loaded: {post_trade['executions']}, "
        f"clearing: {post_trade['clearing_records']}"
    )
    print(
        f"Matched: {post_trade['matched']}, breaks: {post_trade['breaks']} "
        f"{post_trade['breaks_by_type']}"
    )
    print(
        f"Total P&L: realised {post_trade['realised_pnl']:.2f}, "
        f"unrealised {post_trade['unrealised_pnl']:.2f}, "
        f"total {post_trade['total_pnl']:.2f}"
    )
    quarantined = sum(
        len(rows) for rows in summary["quarantined"].values()
    )
    print(f"Quarantined rows: {quarantined}, reference notes: {len(summary['notes'])}")
    print("Report written to posttrade_orchestrated_report.json")


if __name__ == "__main__":
    main()
