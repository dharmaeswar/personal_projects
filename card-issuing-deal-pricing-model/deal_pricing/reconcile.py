"""Reconciliation: Python totals must agree with SQL totals.

Loads monthly economics into SQLite, recomputes portfolio totals with a
SQL GROUP BY, and compares them with the Python-computed totals. The run
fails if any total disagrees by more than $0.01 — the same discipline the
JD asks for when turning SQL pulls into reusable datasets: the numbers in
the deck must tie back to the data.
"""
import sqlite3
from decimal import Decimal

from .economics import MonthEconomics, money

TOLERANCE = Decimal("0.01")


def load_to_sqlite(months: list, db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS monthly_economics ("
        " customer TEXT, month TEXT, tpv TEXT, transactions INTEGER,"
        " interchange TEXT, network_fees TEXT, bank_cost TEXT,"
        " processing_cost TEXT, fixed_cost TEXT, gross_profit TEXT)"
    )
    for m in months:
        conn.execute(
            "INSERT INTO monthly_economics VALUES (?,?,?,?,?,?,?,?,?,?)",
            (m.customer, m.month, str(m.tpv), m.transactions,
             str(m.interchange), str(m.network_fees), str(m.bank_cost),
             str(m.processing_cost), str(m.fixed_cost), str(m.gross_profit)),
        )
    conn.commit()
    return conn


def sql_totals(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT SUM(CAST(tpv AS REAL)), SUM(transactions),"
        " SUM(CAST(interchange AS REAL)), SUM(CAST(network_fees AS REAL)),"
        " SUM(CAST(bank_cost AS REAL)), SUM(CAST(processing_cost AS REAL)),"
        " SUM(CAST(fixed_cost AS REAL)), SUM(CAST(gross_profit AS REAL))"
        " FROM monthly_economics"
    ).fetchone()
    keys = ("tpv", "transactions", "interchange", "network_fees", "bank_cost",
            "processing_cost", "fixed_cost", "gross_profit")
    out = {}
    for key, value in zip(keys, row):
        out[key] = money(value) if value is not None else Decimal("0.00")
    out["transactions"] = int(out["transactions"])
    return out


def reconcile(python_totals: dict, conn: sqlite3.Connection) -> list:
    """Return a list of mismatch strings; empty means reconciled."""
    sql = sql_totals(conn)
    mismatches = []
    for key in ("tpv", "interchange", "network_fees", "bank_cost",
                "processing_cost", "fixed_cost", "gross_profit"):
        diff = abs(Decimal(str(python_totals[key])) - sql[key])
        if diff > TOLERANCE:
            mismatches.append(
                f"{key}: Python {python_totals[key]} vs SQL {sql[key]} "
                f"(diff {diff} > {TOLERANCE})"
            )
    if python_totals["transactions"] != sql["transactions"]:
        mismatches.append(
            f"transactions: Python {python_totals['transactions']} "
            f"vs SQL {sql['transactions']}"
        )
    return mismatches
