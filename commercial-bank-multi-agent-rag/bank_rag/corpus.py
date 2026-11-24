"""Synthetic commercial-bank corpus.

All borrowers, figures and memos are invented for this project. No real
bank, borrower or account data is used. Figures are in $ millions.
"""

BORROWERS = {
    "Northgate Logistics Group": {
        "revenue": 850.0,
        "ebitda": 120.0,
        "total_debt": 420.0,
        "cash": 60.0,
        "interest_expense": 30.0,
        "max_leverage": 4.0,
        "min_interest_coverage": 2.5,
    },
    "BlueRock Packaging Co": {
        "revenue": 640.0,
        "ebitda": 96.0,
        "total_debt": 384.0,
        "cash": 25.0,
        "interest_expense": 48.0,
        "max_leverage": 3.5,
        "min_interest_coverage": 2.0,
    },
    "Summit Ridge Manufacturing": {
        "revenue": 1200.0,
        "ebitda": 150.0,
        "total_debt": 300.0,
        "cash": 90.0,
        "interest_expense": 25.0,
        "max_leverage": 3.0,
        "min_interest_coverage": 3.0,
    },
}

MEMOS = {
    "Northgate Logistics Group": (
        "Northgate Logistics Group operates a regional freight fleet across the "
        "upper Midwest. Fuel cost pressure reduced operating margins this year, "
        "but fleet expansion into two new terminals added contracted revenue. "
        "Management expects fuel surcharges to recover most of the cost increase "
        "next quarter. No material litigation is outstanding."
    ),
    "BlueRock Packaging Co": (
        "BlueRock Packaging Co makes corrugated packaging for food producers. "
        "Raw-material price volatility squeezed margins, and a plant outage in "
        "March cut one quarter of production for three weeks. The outage is "
        "resolved and the plant is back at full capacity. Customer concentration "
        "is moderate, with the top customer at 18 percent of revenue."
    ),
    "Summit Ridge Manufacturing": (
        "Summit Ridge Manufacturing builds industrial fasteners. Supply-chain risk "
        "is concentrated in a single-source supplier in Asia for a specialty "
        "alloy; the borrower is dual-sourcing the alloy and holds six months of "
        "safety stock. Order backlog grew 12 percent year over year. The "
        "borrower refinanced its term loan in June at a lower spread."
    ),
}


def financial_statement_text(name, figures):
    """One plain-text fact sentence per figure, so retrieval can cite it."""
    return (
        f"{name} reported revenue of {figures['revenue']:.1f} million dollars. "
        f"{name} reported EBITDA of {figures['ebitda']:.1f} million dollars. "
        f"{name} reported total debt of {figures['total_debt']:.1f} million dollars. "
        f"{name} reported cash of {figures['cash']:.1f} million dollars. "
        f"{name} reported interest expense of {figures['interest_expense']:.1f} million dollars."
    )


def covenant_text(name, figures):
    return (
        f"{name} is subject to a maximum leverage covenant of "
        f"{figures['max_leverage']:.1f}x total debt to EBITDA and a minimum "
        f"interest coverage covenant of {figures['min_interest_coverage']:.1f}x "
        f"EBITDA to interest expense."
    )


def build_corpus():
    """Return a list of documents: {doc_id, borrower, kind, text}."""
    docs = []
    for name, figures in BORROWERS.items():
        docs.append({
            "doc_id": f"{name}|financials",
            "borrower": name,
            "kind": "financials",
            "text": financial_statement_text(name, figures),
        })
        docs.append({
            "doc_id": f"{name}|memo",
            "borrower": name,
            "kind": "memo",
            "text": MEMOS[name],
        })
        docs.append({
            "doc_id": f"{name}|covenant",
            "borrower": name,
            "kind": "covenant",
            "text": covenant_text(name, figures),
        })
    return docs
