"""Seeded synthetic investment data.

Everything here is invented and deterministic (seed 42): no real issuer,
security, trade, or yield data. Bad rows are planted on purpose so each
validation check has something real to catch.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from .security_master import cusip_check_digit, isin_check_digit

AS_OF = date(2026, 11, 20)

ISSUERS = [
    ("Acme Corp", "Corporate Bond"),
    ("Beacon Utilities", "Corporate Bond"),
    ("Cascade Rail", "Corporate Bond"),
    ("Delta Foods", "Corporate Bond"),
    ("Everest Health", "Corporate Bond"),
    ("Frontier Energy", "Corporate Bond"),
    ("US Treasury", "Treasury"),
    ("Harbor City", "Municipal"),
]

TENORS = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "7Y", "10Y", "20Y", "30Y"]


def _cusip(rng: random.Random) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    body = "".join(rng.choice(alphabet) for _ in range(8))
    return body + str(cusip_check_digit(body))


def _isin(rng: random.Random, cusip: str) -> str:
    body = "US" + cusip
    return body + str(isin_check_digit(body))


def build_security_master(rng: random.Random | None = None) -> list[dict]:
    """40 securities: 36 clean, 4 with planted defects."""
    rng = rng or random.Random(42)
    rows: list[dict] = []
    for i in range(36):
        issuer, asset_class = ISSUERS[i % len(ISSUERS)]
        cusip = _cusip(rng)
        issue = date(2018, 1, 1) + timedelta(days=rng.randrange(0, 2500))
        maturity = issue + timedelta(days=365 * rng.choice([2, 3, 5, 7, 10, 20, 30]))
        rows.append(
            {
                "security_id": f"SEC-{1000 + i}",
                "cusip": cusip,
                "isin": _isin(rng, cusip),
                "ticker": issuer.split()[0].upper()[:4],
                "issuer": issuer,
                "asset_class": asset_class,
                "coupon_rate": round(rng.uniform(1.5, 7.5), 3),
                "issue_date": issue.isoformat(),
                "maturity_date": maturity.isoformat(),
                "face_value": float(rng.choice([1000, 5000, 10000, 100000])),
                "currency": "USD",
                "status": "Active" if maturity > AS_OF else "Matured",
            }
        )
    # Planted defects, one per row.
    bad_cusip = dict(rows[0])
    bad_cusip["security_id"] = "SEC-9001"
    bad_cusip["cusip"] = bad_cusip["cusip"][:8] + str(
        (int(bad_cusip["cusip"][8]) + 1) % 10
    )
    rows.append(bad_cusip)  # bad CUSIP check digit

    dup = dict(rows[1])
    dup["security_id"] = "SEC-9002"
    rows.append(dup)  # duplicate CUSIP, new id

    bad_dates = dict(rows[2])
    bad_dates["security_id"] = "SEC-9003"
    bad_dates["cusip"] = _cusip(rng)
    bad_dates["isin"] = _isin(rng, bad_dates["cusip"])
    bad_dates["issue_date"], bad_dates["maturity_date"] = (
        bad_dates["maturity_date"],
        bad_dates["issue_date"],
    )
    rows.append(bad_dates)  # maturity before issue

    bad_coupon = dict(rows[3])
    bad_coupon["security_id"] = "SEC-9004"
    bad_coupon["cusip"] = _cusip(rng)
    bad_coupon["isin"] = _isin(rng, bad_coupon["cusip"])
    bad_coupon["coupon_rate"] = -2.5
    bad_coupon["face_value"] = 0.0
    rows.append(bad_coupon)  # negative coupon, zero face value
    return rows


def build_trades(
    securities: list[dict], rng: random.Random | None = None
) -> list[dict]:
    """60 trades: 55 clean, 5 with planted defects."""
    rng = rng or random.Random(42)
    ids = [s["security_id"] for s in securities[:36]]
    rows: list[dict] = []
    for i in range(55):
        trade_date = AS_OF - timedelta(days=rng.randrange(0, 30))
        rows.append(
            {
                "trade_id": f"TRD-{5000 + i}",
                "security_id": rng.choice(ids),
                "trade_date": trade_date.isoformat(),
                "settlement_date": (trade_date + timedelta(days=1)).isoformat(),
                "quantity": float(rng.choice([100, 500, 1000, 5000])),
                "price": round(rng.uniform(85.0, 112.0), 4),
                "side": rng.choice(["BUY", "SELL"]),
                "counterparty": rng.choice(["Bank A", "Bank B", "Broker C"]),
                "portfolio_manager": f"PM-{rng.randrange(1, 6)}",
            }
        )
    bad_settle = dict(rows[0])
    bad_settle["trade_id"] = "TRD-9901"
    bad_settle["settlement_date"] = (
        date.fromisoformat(bad_settle["trade_date"]) - timedelta(days=2)
    ).isoformat()
    rows.append(bad_settle)  # settles before it trades

    dup = dict(rows[1])
    rows.append(dup)  # duplicate trade id

    orphan = dict(rows[2])
    orphan["trade_id"] = "TRD-9903"
    orphan["security_id"] = "SEC-9999"
    rows.append(orphan)  # security not in the master

    bad_qty = dict(rows[3])
    bad_qty["trade_id"] = "TRD-9904"
    bad_qty["quantity"] = 0.0
    bad_qty["price"] = -99.5
    rows.append(bad_qty)  # zero quantity, negative price

    future = dict(rows[4])
    future["trade_id"] = "TRD-9905"
    future["trade_date"] = (AS_OF + timedelta(days=3)).isoformat()
    future["settlement_date"] = (AS_OF + timedelta(days=4)).isoformat()
    rows.append(future)  # trade dated in the future
    return rows


def build_yield_curves() -> tuple[list[dict], list[dict]]:
    """Prior-day and current-day par yield curves.

    Current day has one missing tenor (7Y), one stale point (20Y still
    stamped yesterday), and one outlier (10Y jumped 80bp overnight).
    """
    prior = [2.10, 2.35, 2.60, 3.05, 3.40, 3.85, 4.05, 4.20, 4.55, 4.70]
    current = [2.12, 2.36, 2.61, 3.06, 3.41, 3.86, None, 4.20, 4.56, 4.71]
    prior_day = AS_OF - timedelta(days=1)
    prior_rows = [
        {
            "tenor": t,
            "yield_pct": y,
            "as_of_date": prior_day.isoformat(),
            "source": "Pricing Vendor",
        }
        for t, y in zip(TENORS, prior)
    ]
    current_rows = []
    for t, y in zip(TENORS, current):
        if y is None:
            continue  # 7Y missing today
        stamp = AS_OF
        if t == "20Y":
            stamp = prior_day  # stale point
        if t == "10Y":
            y = 5.00  # 80bp jump vs 4.20 yesterday
        current_rows.append(
            {
                "tenor": t,
                "yield_pct": y,
                "as_of_date": stamp.isoformat(),
                "source": "Pricing Vendor",
            }
        )
    return prior_rows, current_rows


def build_warehouse_snapshots(
    securities: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Legacy extract vs new investment data warehouse snapshot.

    Same 36 clean securities, priced identically, except: one security is
    missing from the warehouse, one is an orphan in the warehouse, and one
    has a different market value (price moved in the warehouse load).
    """
    legacy = [
        {
            "security_id": s["security_id"],
            "market_value": round(s["face_value"] * 1.02, 2),
            "price": 102.0,
        }
        for s in securities[:36]
    ]
    warehouse = [dict(r) for r in legacy]
    warehouse = [r for r in warehouse if r["security_id"] != "SEC-1005"]
    warehouse.append(
        {"security_id": "SEC-8888", "market_value": 5100.00, "price": 102.0}
    )
    for r in warehouse:
        if r["security_id"] == "SEC-1010":
            r["market_value"] = round(r["market_value"] * 1.10, 2)
    return legacy, warehouse


def build_novel_datasets(
    securities: list[dict], rng: random.Random | None = None
) -> dict[str, list[dict]]:
    """Three novel vendor datasets, one per source, each shaped differently.

    This is what a data-services team onboards: a new feed arrives with its
    own columns, grain and quirks, and the team profiles it, validates it
    and wires it into the platform. Each dataset has one planted defect so
    the onboarding checks have something real to catch.
    """
    rng = rng or random.Random(42)
    clean = securities[:36]

    # ESG scores feed (vendor: "Sustainability Data Co."): one score per
    # security, stamped as-of today. Planted: one missing governance score,
    # one environmental score above 100.
    esg = []
    for s in clean:
        esg.append(
            {
                "security_id": s["security_id"],
                "esg_score": round(rng.uniform(35.0, 92.0), 1),
                "environmental": round(rng.uniform(30.0, 95.0), 1),
                "social": round(rng.uniform(30.0, 95.0), 1),
                "governance": round(rng.uniform(30.0, 95.0), 1),
                "as_of_date": AS_OF.isoformat(),
                "source": "Sustainability Data Co.",
            }
        )
    esg[5]["governance"] = None  # missing governance score
    esg[11]["environmental"] = 104.5  # score above 100

    # Corporate actions feed (vendor: "Actions Wire"): one row per action.
    # Planted: one duplicate action_id, one action on an unknown security.
    actions = []
    for i, s in enumerate(clean[:12]):
        actions.append(
            {
                "action_id": f"ACT-{7000 + i}",
                "security_id": s["security_id"],
                "action_type": rng.choice(["COUPON", "DIVIDEND", "SPLIT"]),
                "ex_date": (AS_OF + timedelta(days=rng.randrange(1, 30))).isoformat(),
                "amount": round(rng.uniform(0.5, 12.0), 2),
                "source": "Actions Wire",
            }
        )
    dup = dict(actions[2])
    actions.append(dup)  # duplicate action_id
    orphan = dict(actions[3])
    orphan["action_id"] = "ACT-7999"
    orphan["security_id"] = "SEC-9999"
    actions.append(orphan)  # action on an unknown security

    # FX spot rates feed (vendor: "FX Rates Ltd."): one row per pair.
    # Planted: one stale row (stamped yesterday), one missing rate.
    pairs = [
        ("EURUSD", 1.0842), ("GBPUSD", 1.2715), ("USDJPY", 151.32),
        ("USDCHF", 0.8841), ("AUDUSD", 0.6523), ("USDCAD", 1.3598),
    ]
    fx = []
    for pair, rate in pairs:
        fx.append(
            {
                "pair": pair,
                "spot_rate": rate,
                "as_of_date": AS_OF.isoformat(),
                "source": "FX Rates Ltd.",
            }
        )
    fx[3]["as_of_date"] = (AS_OF - timedelta(days=1)).isoformat()  # stale
    fx[5]["spot_rate"] = None  # missing rate

    return {"esg_scores": esg, "corporate_actions": actions, "fx_rates": fx}
