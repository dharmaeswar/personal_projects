"""Monthly reporting: the support files behind the sales deck.

Writes CSVs that open directly in Excel plus a plain-text stakeholder
summary: monthly economics per customer, the portfolio forecast, deal
pricing for the negotiation in flight, and variance commentary.
"""
import csv
import os
from decimal import Decimal

from .variance import Variance


def write_monthly_csv(months: list, path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["customer", "month", "tpv", "transactions", "interchange",
                    "network_fees", "bank_cost", "processing_cost",
                    "fixed_cost", "gross_profit", "gross_margin_pct"])
        for m in months:
            w.writerow([m.customer, m.month, f"{m.tpv:.2f}", m.transactions,
                        f"{m.interchange:.2f}", f"{m.network_fees:.2f}",
                        f"{m.bank_cost:.2f}", f"{m.processing_cost:.2f}",
                        f"{m.fixed_cost:.2f}", f"{m.gross_profit:.2f}",
                        f"{m.gross_margin_pct:.2f}"])


def write_forecast_csv(rows: list, path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["customer", "month", "active_cards", "tpv",
                    "transactions", "gross_profit"])
        for r in rows:
            w.writerow([r.customer, r.month, r.active_cards, f"{r.tpv:.2f}",
                        r.transactions, f"{r.gross_profit:.2f}"])


def write_summary(variances: list, totals: dict, path: str) -> None:
    lines = ["MONTHLY CUSTOMER PERFORMANCE SUMMARY", ""]
    lines.append(
        f"Portfolio: TPV ${totals['tpv']:,.2f} | interchange "
        f"${totals['interchange']:,.2f} | gross profit "
        f"${totals['gross_profit']:,.2f} "
        f"({totals['gross_margin_pct']}% margin) | "
        f"{totals['transactions']:,} transactions."
    )
    lines.append("")
    for v in variances:
        lines.append(v.commentary())
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
