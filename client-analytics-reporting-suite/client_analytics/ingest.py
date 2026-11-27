"""Load the synthetic datasets into SQLite (one table per source)."""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY, segment TEXT, region TEXT, join_month TEXT);
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY, client_id TEXT, account_type TEXT,
    open_month TEXT);
CREATE TABLE IF NOT EXISTS transactions (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT, txn_id TEXT, account_id TEXT,
    month TEXT, channel TEXT, txn_type TEXT, amount REAL);
CREATE TABLE IF NOT EXISTS ops_events (
    event_id TEXT PRIMARY KEY, client_id TEXT, month TEXT,
    event_type TEXT, resolution_days INTEGER);
"""


def load(conn, data):
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO clients VALUES (:client_id, :segment, :region, :join_month)",
        data["clients"])
    conn.executemany(
        "INSERT INTO accounts VALUES (:account_id, :client_id, :account_type, :open_month)",
        data["accounts"])
    conn.executemany(
        "INSERT INTO transactions (txn_id, account_id, month, channel, txn_type, amount)"
        " VALUES (:txn_id, :account_id, :month, :channel, :txn_type, :amount)",
        data["transactions"])
    conn.executemany(
        "INSERT INTO ops_events VALUES (:event_id, :client_id, :month, :event_type, :resolution_days)",
        data["ops_events"])
    conn.commit()


def open_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
