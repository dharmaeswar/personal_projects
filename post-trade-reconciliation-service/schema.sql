-- Post-Trade Reconciliation Service: PostgreSQL schema.
--
-- Production DDL for the tables the service persists. Local runs and
-- tests use SQLite (see posttrade/store.py) with the same tables and
-- columns, so the service runs anywhere without a database server.

CREATE TABLE IF NOT EXISTS enriched_trades (
    exec_id      TEXT PRIMARY KEY,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    price        NUMERIC(18, 6) NOT NULL,
    trade_date   DATE NOT NULL,
    venue        TEXT NOT NULL,
    account      TEXT NOT NULL,
    notional     NUMERIC(18, 2) NOT NULL,
    enriched     BOOLEAN NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_enriched_trades_symbol_date
    ON enriched_trades (symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_enriched_trades_account
    ON enriched_trades (account, trade_date);

CREATE TABLE IF NOT EXISTS breaks (
    id           SERIAL PRIMARY KEY,
    break_type   TEXT NOT NULL CHECK (break_type IN (
                     'MISSING_CLEARING', 'MISSING_EXECUTION',
                     'QTY_MISMATCH', 'PRICE_BREAK')),
    exec_id      TEXT REFERENCES enriched_trades (exec_id),
    clearing_id  TEXT,
    detail       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_breaks_type ON breaks (break_type);

CREATE TABLE IF NOT EXISTS positions (
    account      TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    net_quantity INTEGER NOT NULL,
    average_cost NUMERIC(18, 6) NOT NULL,
    multiplier   INTEGER NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account, symbol)
);

CREATE TABLE IF NOT EXISTS pnl_snapshots (
    account      TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    realised     NUMERIC(18, 2) NOT NULL,
    unrealised   NUMERIC(18, 2) NOT NULL,
    net_quantity INTEGER NOT NULL,
    snapshot_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account, symbol)
);
