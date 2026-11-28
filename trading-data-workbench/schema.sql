-- Trading data workbench schema.
-- Written in standard SQL: runs unchanged on PostgreSQL (the target store
-- for a production deployment) and on SQLite (the demo store used here).
-- All data is synthetic; no real market data is used.

CREATE TABLE IF NOT EXISTS instruments (
    symbol      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    currency    TEXT NOT NULL,
    exchange    TEXT NOT NULL,
    base_price  NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id     SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL REFERENCES instruments (symbol),
    ts     TIMESTAMPTZ NOT NULL,
    bid    NUMERIC NOT NULL,
    ask    NUMERIC NOT NULL,
    last   NUMERIC NOT NULL,
    volume INTEGER NOT NULL,
    UNIQUE (symbol, ts)
);

CREATE INDEX IF NOT EXISTS idx_quotes_symbol_ts ON quotes (symbol, ts);

CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL REFERENCES instruments (symbol),
    side            TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty             INTEGER NOT NULL CHECK (qty > 0),
    order_type      TEXT NOT NULL CHECK (order_type IN ('MARKET', 'LIMIT')),
    limit_price     NUMERIC,
    status          TEXT NOT NULL,
    filled_qty      INTEGER NOT NULL DEFAULT 0,
    filled_price    NUMERIC,
    idempotency_key TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL
);
