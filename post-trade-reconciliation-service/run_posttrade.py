"""Demo runner: one seeded intraday post-trade cycle.

Runs 8 synthetic executions against 7 synthetic clearing records,
prints the reconciliation outcome, positions and P&L, and writes
posttrade_report.json. All data is synthetic; nothing here claims a
live trading connection or production use.
"""

import json

from posttrade.models import ClearingRecord, Execution
from posttrade.service import run_post_trade

EXECUTIONS = [
    Execution("E1", "AAPL 260117C00250000", "BUY", 10, 4.20, "2026-11-24", "CBOE", "ACC-001"),
    Execution("E2", "AAPL 260117C00250000", "SELL", 4, 4.50, "2026-11-24", "CBOE", "ACC-001"),
    Execution("E3", "SPX 260117P00590000", "BUY", 5, 12.30, "2026-11-24", "CBOE", "ACC-001"),
    Execution("E4", "MSFT 260117C00420000", "BUY", 20, 2.10, "2026-11-24", "NYSE ARCA", "ACC-002"),
    Execution("E5", "AAPL", "BUY", 100, 250.00, "2026-11-24", "NASDAQ", "ACC-001"),
    Execution("E6", "AAPL 260117C00250000", "BUY", 6, 4.25, "2026-11-24", "CBOE", "ACC-001"),
    Execution("E7", "SPX 260117P00590000", "SELL", 2, 12.80, "2026-11-24", "CBOE", "ACC-001"),
    Execution("E8", "XYZ 260117C00010000", "BUY", 3, 1.00, "2026-11-24", "CBOE", "ACC-001"),
]

CLEARING = [
    ClearingRecord("C1", "AAPL 260117C00250000", "BUY", 10, 4.20, "2026-11-24", "ACC-001", 1.10),
    ClearingRecord("C2", "AAPL 260117C00250000", "SELL", 4, 4.52, "2026-11-24", "ACC-001", 0.44),
    ClearingRecord("C3", "SPX 260117P00590000", "BUY", 5, 12.30, "2026-11-24", "ACC-001", 0.55),
    ClearingRecord("C4", "MSFT 260117C00420000", "BUY", 20, 2.10, "2026-11-24", "ACC-002", 2.20),
    ClearingRecord("C5", "AAPL", "BUY", 100, 250.00, "2026-11-24", "ACC-001", 0.00),
    ClearingRecord("C6", "AAPL 260117C00250000", "BUY", 5, 4.25, "2026-11-24", "ACC-001", 0.55),
    ClearingRecord("C7", "MSFT 260117C00420000", "SELL", 10, 2.40, "2026-11-24", "ACC-002", 1.10),
]

MARKS = {
    "AAPL 260117C00250000": 4.60,
    "SPX 260117P00590000": 12.00,
    "MSFT 260117C00420000": 2.25,
    "AAPL": 252.00,
}


def main():
    report = run_post_trade(EXECUTIONS, CLEARING, MARKS)
    with open("posttrade_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"Executions: {report['executions']}, clearing: {report['clearing_records']}")
    print(f"Matched: {report['matched']}, breaks: {report['breaks']} {report['breaks_by_type']}")
    for pos in report["positions"]:
        print(
            f"Position {pos['account']} {pos['symbol']}: "
            f"net {pos['net_quantity']} @ {pos['average_cost']}"
        )
    for row in report["pnl"]:
        print(
            f"P&L {row['account']} {row['symbol']}: realised "
            f"{row['realised']:.2f}, unrealised {row['unrealised']:.2f}"
        )
    print(
        f"Total P&L: realised {report['realised_pnl']:.2f}, "
        f"unrealised {report['unrealised_pnl']:.2f}, "
        f"total {report['total_pnl']:.2f}"
    )
    print("Report written to posttrade_report.json")


if __name__ == "__main__":
    main()
