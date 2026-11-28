"""Seeded synthetic trading data for the surveillance lakehouse.

All data is synthetic and seeded (seed 42). No real market data, orders,
accounts, or CAT submissions are involved. The defects are planted on
purpose so the ingest and modelling stages have real work to do.
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import pandas as pd

SEED = 42
DAYS = [date(2026, 11, 16) + timedelta(days=i) for i in range(5)]  # Mon-Fri

INSTRUMENTS = [
    ("AAPL", "Apple Inc", "NASDAQ", "USD", "Technology"),
    ("MSFT", "Microsoft Corp", "NASDAQ", "USD", "Technology"),
    ("NVDA", "NVIDIA Corp", "NASDAQ", "USD", "Technology"),
    ("JPM", "JPMorgan Chase & Co", "NYSE", "USD", "Financials"),
    ("SPY", "SPDR S&P 500 ETF", "NYSE Arca", "USD", "ETF"),
    ("TLT", "iShares 20+ Year Treasury ETF", "NASDAQ", "USD", "ETF"),
]

BASE_PRICE = {"AAPL": 262.0, "MSFT": 512.0, "NVDA": 198.0,
              "JPM": 298.0, "SPY": 685.0, "TLT": 88.0}

ACCOUNTS = [f"ACC-{i:03d}" for i in range(1, 11)]

ORDER_COLUMNS = ["order_id", "account_id", "symbol", "side", "qty",
                 "limit_price", "order_ts", "event", "trade_date",
                 "ingested_at"]
EXEC_COLUMNS = ["exec_id", "order_id", "symbol", "qty", "price",
                "exec_ts", "trade_date", "ingested_at"]
TRADE_COLUMNS = ["trade_id", "symbol", "price", "qty", "trade_ts",
                 "trade_date", "ingested_at"]


def _market_time(rng: random.Random, day: date) -> datetime:
    """A random timestamp inside US market hours on the given day."""
    minutes = rng.randrange(0, 390)  # 09:30-16:00
    return datetime.combine(day, time(9, 30)) + timedelta(minutes=minutes)


def generate(seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Generate the full seeded feed: orders, executions, market trades."""
    rng = random.Random(seed)
    orders, executions, trades = [], [], []
    order_seq, exec_seq, trade_seq = 0, 0, 0

    for day in DAYS:
        # --- orders: 400 per day ---
        for _ in range(400):
            order_seq += 1
            symbol = rng.choice([s for s, *_ in INSTRUMENTS])
            account = rng.choice(ACCOUNTS)
            # ACC-007 / AAPL is reserved for the planted wash pattern
            # below, so the test signal stays unambiguous: random orders
            # never add buy/sell noise to that account-symbol pair.
            if account == "ACC-007" and symbol == "AAPL":
                symbol = rng.choice(
                    [s for s, *_ in INSTRUMENTS if s != "AAPL"])
            side = rng.choice(["BUY", "SELL"])
            qty = rng.randrange(1, 101) * 10
            base = BASE_PRICE[symbol]
            price = round(base * rng.uniform(0.98, 1.02), 2)
            ts = _market_time(rng, day)
            event = "CANCEL" if rng.random() < 0.08 else "NEW"
            orders.append({
                "order_id": f"ORD-{order_seq:06d}",
                "account_id": account,
                "symbol": symbol, "side": side, "qty": qty,
                "limit_price": price, "order_ts": ts, "event": event,
                "trade_date": day,
                "ingested_at": ts + timedelta(minutes=rng.randrange(1, 30)),
            })
        # Planted wash-trade pattern: ACC-007 buys and sells the same
        # symbol in matched size on the same day, every day. The gold
        # layer flags it as a surveillance candidate; it is synthetic.
        for _ in range(4):
            for side in ("BUY", "SELL"):
                order_seq += 1
                ts = _market_time(rng, day)
                orders.append({
                    "order_id": f"ORD-{order_seq:06d}",
                    "account_id": "ACC-007", "symbol": "AAPL",
                    "side": side, "qty": 500,
                    "limit_price": round(BASE_PRICE["AAPL"] * 1.001, 2),
                    "order_ts": ts, "event": "NEW", "trade_date": day,
                    "ingested_at": ts + timedelta(minutes=5),
                })
        # --- executions: ~70% of the day's NEW orders execute once ---
        day_orders = [o for o in orders
                      if o["trade_date"] == day and o["event"] == "NEW"]
        for o in day_orders:
            if rng.random() > 0.70:
                continue
            exec_seq += 1
            exec_qty = o["qty"] if rng.random() < 0.7 else o["qty"] // 2
            executions.append({
                "exec_id": f"EXE-{exec_seq:06d}",
                "order_id": o["order_id"], "symbol": o["symbol"],
                "qty": exec_qty,
                "price": round(o["limit_price"] * rng.uniform(0.999, 1.001), 2),
                "exec_ts": o["order_ts"] + timedelta(seconds=rng.randrange(1, 600)),
                "trade_date": day,
                "ingested_at": o["ingested_at"] + timedelta(minutes=2),
            })
        # --- market tape: 300 trades per day ---
        for _ in range(300):
            trade_seq += 1
            symbol = rng.choice([s for s, *_ in INSTRUMENTS])
            base = BASE_PRICE[symbol]
            trades.append({
                "trade_id": f"TRD-{trade_seq:06d}",
                "symbol": symbol,
                "price": round(base * rng.uniform(0.98, 1.02), 2),
                "qty": rng.randrange(1, 51) * 10,
                "trade_ts": _market_time(rng, day),
                "trade_date": day,
                "ingested_at": datetime.combine(day, time(16, 5)),
            })

    orders_df = pd.DataFrame(orders)
    executions_df = pd.DataFrame(executions)
    trades_df = pd.DataFrame(trades)

    # --- planted defects (the pipeline must quarantine all of them) ---
    defects = []
    # 5 duplicate order rows: same order_id, later ingest, different qty
    dupes = orders_df.iloc[[10, 500, 900, 1300, 1700]].copy()
    dupes["qty"] = dupes["qty"] + 10
    dupes["ingested_at"] = dupes["ingested_at"] + timedelta(hours=1)
    defects.append(("duplicate", dupes))
    # 3 rows with a missing account
    missing = orders_df.iloc[[20, 600, 1000]].copy()
    missing["account_id"] = None
    defects.append(("missing_account", missing))
    # 2 rows with a non-positive quantity
    bad_qty = orders_df.iloc[[30, 700]].copy()
    bad_qty["qty"] = 0
    defects.append(("bad_qty", bad_qty))
    # 2 rows whose trade_date disagrees with the order timestamp date
    bad_date = orders_df.iloc[[40, 800]].copy()
    bad_date["trade_date"] = bad_date["trade_date"] + timedelta(days=1)
    defects.append(("date_mismatch", bad_date))

    extra = pd.concat([d for _, d in defects], ignore_index=True)
    orders_df = pd.concat([orders_df, extra], ignore_index=True)

    # 2 late-arriving executions (ingested 2 days after the event).
    # Both copies are kept: silver dedupe keeps the latest ingest, and
    # the DQ report counts them as late arrivals.
    late = executions_df.iloc[[5, 50]].copy()
    late["ingested_at"] = late["ingested_at"] + timedelta(days=2)
    executions_df = pd.concat([executions_df, late], ignore_index=True)

    return {"orders": orders_df, "executions": executions_df,
            "trades": trades_df}


def dim_instrument() -> pd.DataFrame:
    return pd.DataFrame(
        INSTRUMENTS,
        columns=["symbol", "name", "exchange", "currency", "sector"],
    )


def dim_account() -> pd.DataFrame:
    return pd.DataFrame({
        "account_id": ACCOUNTS,
        "account_type": ["Proprietary"] * 5 + ["Client"] * 5,
        "region": ["US"] * 10,
    })
