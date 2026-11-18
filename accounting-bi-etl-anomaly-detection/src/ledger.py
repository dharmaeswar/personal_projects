"""Ledger storage: staging, quarantine, balance checks, trial balance.

SQLite (standard library only) holds the staged lines so the pipeline runs
anywhere. Gold tables are built only from clean lines: schema-valid, from a
balanced journal, and not a duplicate.
"""

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_lines (
    entry_id TEXT PRIMARY KEY,
    journal_id TEXT NOT NULL,
    posting_date TEXT NOT NULL,
    fiscal_period TEXT NOT NULL,
    account TEXT NOT NULL,
    debit REAL NOT NULL,
    credit REAL NOT NULL,
    currency TEXT NOT NULL,
    source_system TEXT NOT NULL,
    description TEXT,
    posted_by TEXT
);
CREATE TABLE IF NOT EXISTS quarantine (
    entry_id TEXT,
    journal_id TEXT,
    reason TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journal_flags (
    journal_id TEXT PRIMARY KEY,
    total_debit REAL NOT NULL,
    total_credit REAL NOT NULL,
    balanced INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS line_flags (
    entry_id TEXT PRIMARY KEY,
    flag TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""

BALANCE_TOLERANCE = 0.01


def open_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def insert_lines(conn, lines):
    """Insert validated lines; returns the number inserted."""
    conn.executemany(
        "INSERT OR REPLACE INTO raw_lines VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                line["entry_id"],
                line["journal_id"],
                line["posting_date"],
                line["fiscal_period"],
                line["account"],
                float(line["debit"]),
                float(line["credit"]),
                line["currency"],
                line["source_system"],
                line.get("description", ""),
                line.get("posted_by", ""),
            )
            for line in lines
        ],
    )
    conn.commit()
    return len(lines)


def quarantine_line(conn, line, reason):
    import json

    conn.execute(
        "INSERT INTO quarantine VALUES (?,?,?,?)",
        (
            line.get("entry_id"),
            line.get("journal_id"),
            reason,
            json.dumps(line, sort_keys=True),
        ),
    )
    conn.commit()


def check_journal_balances(conn):
    """Flag every journal whose debits do not equal its credits.

    Returns a list of (journal_id, total_debit, total_credit) for the
    unbalanced ones. Balanced journals are recorded too.
    """
    rows = conn.execute(
        "SELECT journal_id, ROUND(SUM(debit), 2), ROUND(SUM(credit), 2)"
        " FROM raw_lines GROUP BY journal_id"
    ).fetchall()
    unbalanced = []
    for journal_id, total_debit, total_credit in rows:
        balanced = abs(total_debit - total_credit) <= BALANCE_TOLERANCE
        conn.execute(
            "INSERT OR REPLACE INTO journal_flags VALUES (?,?,?,?)",
            (journal_id, total_debit, total_credit, int(balanced)),
        )
        if not balanced:
            unbalanced.append((journal_id, total_debit, total_credit))
    conn.commit()
    return unbalanced


def find_duplicates(conn):
    """Return entry_ids that duplicate an earlier line's content.

    A duplicate is an identical (journal, account, amounts, date) line
    posted twice under a different entry_id. (Same entry_id twice is
    caught earlier, at ingest, and quarantined.) The first copy is kept;
    later copies are flagged and excluded from gold.
    """
    dup_ids = set()
    seen_keys = {}
    for row in conn.execute(
        "SELECT entry_id, journal_id, account, debit, credit, posting_date"
        " FROM raw_lines ORDER BY rowid"
    ):
        key = row[1:]
        if key in seen_keys:
            dup_ids.add(row[0])
        else:
            seen_keys[key] = row[0]
    return sorted(dup_ids)


def clean_entry_ids(conn):
    """Entry ids usable for gold: in a balanced journal and not a duplicate."""
    unbalanced = {
        row[0] for row in conn.execute("SELECT journal_id FROM journal_flags WHERE balanced = 0")
    }
    dups = set(find_duplicates(conn))
    rows = conn.execute("SELECT entry_id, journal_id FROM raw_lines").fetchall()
    return [entry_id for entry_id, journal_id in rows if journal_id not in unbalanced and entry_id not in dups]


def trial_balance(conn, entry_ids):
    """Trial balance by account over the clean lines.

    Returns a list of dicts with debit, credit and net (debit - credit).
    A balanced book has total debits == total credits.
    """
    if not entry_ids:
        return []
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"SELECT account, ROUND(SUM(debit), 2), ROUND(SUM(credit), 2)"
        f" FROM raw_lines WHERE entry_id IN ({placeholders})"
        " GROUP BY account ORDER BY account",
        entry_ids,
    ).fetchall()
    return [
        {"account": account, "debit": debit, "credit": credit, "net": round(debit - credit, 2)}
        for account, debit, credit in rows
    ]
