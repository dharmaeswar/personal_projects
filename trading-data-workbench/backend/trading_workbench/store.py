"""SQLite-backed store for the trading data workbench.

The schema in ``schema.sql`` is written in standard SQL and runs unchanged on
PostgreSQL; the demo runs it on SQLite so the service starts with no external
database. All data is synthetic and seeded deterministically — no real market
data, prices, or positions are used.
"""

import random
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

INSTRUMENTS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "asset_class": "Equity", "currency": "USD", "exchange": "NASDAQ", "base_price": 232.50},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "asset_class": "Equity", "currency": "USD", "exchange": "NASDAQ", "base_price": 428.10},
    {"symbol": "NVDA", "name": "NVIDIA Corp.", "asset_class": "Equity", "currency": "USD", "exchange": "NASDAQ", "base_price": 131.25},
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "asset_class": "Equity", "currency": "USD", "exchange": "NYSE", "base_price": 244.80},
    {"symbol": "XOM", "name": "Exxon Mobil Corp.", "asset_class": "Equity", "currency": "USD", "exchange": "NYSE", "base_price": 118.40},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "asset_class": "ETF", "currency": "USD", "exchange": "NYSE Arca", "base_price": 598.30},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "asset_class": "ETF", "currency": "USD", "exchange": "NYSE Arca", "base_price": 244.60},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "asset_class": "Fixed Income", "currency": "USD", "exchange": "NASDAQ", "base_price": 88.90},
]

QUOTE_POINTS = 60  # hourly bars per instrument


def _seed_quotes(symbol, base_price):
    """Deterministic hourly bid/ask/last series ending at the current hour."""
    rng = random.Random(sum(symbol.encode()))
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    price = base_price
    rows = []
    for i in range(QUOTE_POINTS):
        ts = now - timedelta(hours=QUOTE_POINTS - 1 - i)
        price = round(price * (1 + rng.uniform(-0.004, 0.004)), 4)
        mid = price
        rows.append({
            "symbol": symbol,
            "ts": ts.isoformat().replace("+00:00", "Z"),
            "bid": round(mid * 0.9995, 4),
            "ask": round(mid * 1.0005, 4),
            "last": mid,
            "volume": rng.randint(1000, 90000),
        })
    return rows


class Store:
    """Thread-safe store. One lock guards every write; reads are short."""

    def __init__(self):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE instruments (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_class TEXT NOT NULL,
                currency TEXT NOT NULL,
                exchange TEXT NOT NULL,
                base_price REAL NOT NULL
            );
            CREATE TABLE quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL REFERENCES instruments(symbol),
                ts TEXT NOT NULL,
                bid REAL NOT NULL,
                ask REAL NOT NULL,
                last REAL NOT NULL,
                volume INTEGER NOT NULL,
                UNIQUE (symbol, ts)
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL REFERENCES instruments(symbol),
                side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                qty INTEGER NOT NULL CHECK (qty > 0),
                order_type TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
                limit_price REAL,
                status TEXT NOT NULL,
                filled_qty INTEGER NOT NULL DEFAULT 0,
                filled_price REAL,
                idempotency_key TEXT UNIQUE,
                created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _seed(self):
        for inst in INSTRUMENTS:
            self.conn.execute(
                "INSERT INTO instruments VALUES (?,?,?,?,?,?)",
                (inst["symbol"], inst["name"], inst["asset_class"],
                 inst["currency"], inst["exchange"], inst["base_price"]),
            )
            for q in _seed_quotes(inst["symbol"], inst["base_price"]):
                self.conn.execute(
                    "INSERT INTO quotes (symbol, ts, bid, ask, last, volume)"
                    " VALUES (?,?,?,?,?,?)",
                    (q["symbol"], q["ts"], q["bid"], q["ask"], q["last"], q["volume"]),
                )
        self.conn.commit()

    # -- instruments / quotes -------------------------------------------------
    def list_instruments(self):
        rows = self.conn.execute("SELECT * FROM instruments ORDER BY symbol").fetchall()
        return [dict(r) for r in rows]

    def get_instrument(self, symbol):
        row = self.conn.execute(
            "SELECT * FROM instruments WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        return dict(row) if row else None

    def quotes(self, symbol, limit=QUOTE_POINTS):
        rows = self.conn.execute(
            "SELECT symbol, ts, bid, ask, last, volume FROM quotes"
            " WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def latest_quote(self, symbol):
        rows = self.quotes(symbol, limit=1)
        return rows[0] if rows else None

    # -- orders ---------------------------------------------------------------
    def place_order(self, symbol, side, qty, order_type, limit_price, idempotency_key):
        """Insert an order and fill it if the market crosses. Returns the order.

        A repeated idempotency key returns the original order instead of
        creating a duplicate. Raises ValueError on a validation failure.
        """
        symbol = symbol.upper()
        with self.lock:
            if idempotency_key:
                row = self.conn.execute(
                    "SELECT * FROM orders WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if row:
                    return dict(row), True
            if self.get_instrument(symbol) is None:
                raise ValueError(f"unknown symbol: {symbol}")
            quote = self.latest_quote(symbol)
            if quote is None:
                raise ValueError(f"no market data for symbol: {symbol}")
            mid = quote["last"]
            if side == "SELL":
                held = self._position_qty_locked(symbol)
                if qty > held:
                    raise ValueError(
                        f"cannot sell {qty} {symbol}: only {held} held"
                    )
            crosses = order_type == "MARKET" or (
                side == "BUY" and limit_price is not None and limit_price >= mid
            ) or (
                side == "SELL" and limit_price is not None and limit_price <= mid
            )
            status = "filled" if crosses else "open"
            filled_qty = qty if crosses else 0
            filled_price = round(mid, 4) if crosses else None
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            cur = self.conn.execute(
                "INSERT INTO orders (symbol, side, qty, order_type, limit_price,"
                " status, filled_qty, filled_price, idempotency_key, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (symbol, side, qty, order_type, limit_price, status,
                 filled_qty, filled_price, idempotency_key, now),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM orders WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return dict(row), False

    def _position_qty_locked(self, symbol):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN filled_qty"
            " ELSE -filled_qty END), 0) AS qty FROM orders"
            " WHERE symbol = ? AND status = 'filled'",
            (symbol,),
        ).fetchone()
        return row["qty"]

    def list_orders(self):
        rows = self.conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def get_order(self, order_id):
        row = self.conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- positions ------------------------------------------------------------
    def positions(self):
        """Open positions with average cost, market value, unrealised P&L."""
        out = []
        for inst in self.list_instruments():
            symbol = inst["symbol"]
            rows = self.conn.execute(
                "SELECT side, filled_qty, filled_price FROM orders"
                " WHERE symbol = ? AND status = 'filled' ORDER BY id",
                (symbol,),
            ).fetchall()
            qty = 0
            cost = 0.0
            for r in rows:
                if r["side"] == "BUY":
                    qty += r["filled_qty"]
                    cost += r["filled_qty"] * r["filled_price"]
                else:
                    if qty > 0:
                        avg = cost / qty
                        qty -= r["filled_qty"]
                        cost -= r["filled_qty"] * avg
            if qty == 0:
                continue
            avg_cost = round(cost / qty, 4)
            last = self.latest_quote(symbol)["last"]
            market_value = round(qty * last, 2)
            out.append({
                "symbol": symbol,
                "qty": qty,
                "avg_cost": avg_cost,
                "last_price": last,
                "market_value": market_value,
                "unrealized_pnl": round(market_value - cost, 2),
            })
        return out
