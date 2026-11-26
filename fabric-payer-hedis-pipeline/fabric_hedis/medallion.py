"""Fabric medallion layers, local stand-in.

A Fabric Lakehouse holds bronze (raw), silver (cleansed) and gold
(curated) Delta Lake tables; the Fabric Warehouse holds the same data as
relational tables. There is no Fabric workspace here, so SQLite stands in
for both: tables are named bronze_*, silver_*, gold_*, and every write is
recorded in a Delta-style append-only ``delta_log`` (version, operation,
row count) so a load can be replayed or audited. The SQL in
``fabric_hedis/sql/`` is the production Fabric Warehouse equivalent and is
validated structurally by the test suite.
"""

import sqlite3

from .seed import DIAG_CODES

SERVICE_WINDOW_START = "2026-01-01"
SERVICE_WINDOW_END = "2026-10-31"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bronze_members (
    member_id TEXT, sex TEXT, age INTEGER, plan TEXT, diabetes TEXT,
    hypertension TEXT, enrollment_start TEXT, enrollment_end TEXT,
    ingested_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS bronze_claims (
    claim_id TEXT, member_id TEXT, service_date TEXT, diag_code TEXT,
    procedure_code TEXT, billed_amount REAL, adjustment REAL,
    paid_amount REAL, source_file TEXT,
    ingested_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS bronze_labs (
    member_id TEXT, test TEXT, result TEXT, result_date TEXT,
    ingested_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS bronze_screenings (
    member_id TEXT, screening_type TEXT, screening_date TEXT,
    ingested_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS silver_members AS SELECT * FROM bronze_members WHERE 0;
CREATE TABLE IF NOT EXISTS silver_claims AS SELECT * FROM bronze_claims WHERE 0;
CREATE TABLE IF NOT EXISTS silver_labs AS SELECT * FROM bronze_labs WHERE 0;
CREATE TABLE IF NOT EXISTS silver_screenings AS SELECT * FROM bronze_screenings WHERE 0;
CREATE TABLE IF NOT EXISTS quarantine (
    source_table TEXT, record_id TEXT, reason TEXT, payload TEXT,
    quarantined_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS gold_hedis_monthly (
    measure TEXT, measurement_month TEXT, denominator INTEGER,
    numerator INTEGER, rate REAL,
    PRIMARY KEY (measure, measurement_month));
CREATE TABLE IF NOT EXISTS delta_log (
    version INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT,
    operation TEXT, rows_affected INTEGER,
    logged_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS run_log (
    run_id TEXT, step TEXT, status TEXT, detail TEXT,
    logged_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS run_stats (
    measurement_month TEXT PRIMARY KEY, bronze_claims INTEGER,
    silver_claims INTEGER, quarantined INTEGER);
"""


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _log_delta(conn, table_name, operation, rows_affected):
    conn.execute(
        "INSERT INTO delta_log (table_name, operation, rows_affected)"
        " VALUES (?, ?, ?)", (table_name, operation, rows_affected))


def clear_bronze(conn):
    """Empty the bronze tables before a (re)load.

    The inbound files are the full monthly drop, so a re-run replaces
    the bronze layer instead of appending a second copy of the same
    files. Without this, re-running a month would double-count bronze.
    """
    for table in ("bronze_members", "bronze_claims", "bronze_labs",
                  "bronze_screenings"):
        conn.execute("DELETE FROM %s" % table)
        _log_delta(conn, table, "truncate", 0)
    conn.commit()


def load_bronze(conn, table, rows, columns):
    """Append raw rows to a bronze table (no validation here by design)."""
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        "INSERT INTO %s (%s) VALUES (%s)"
        % (table, ", ".join(columns), placeholders),
        [tuple(r[c] for c in columns) for r in rows])
    _log_delta(conn, table, "append", len(rows))
    conn.commit()
    return len(rows)


def _claim_problems(row, member_ids):
    problems = []
    if row["member_id"] not in member_ids:
        problems.append("unknown_member_id")
    try:
        paid = float(row["paid_amount"])
        billed = float(row["billed_amount"])
        adjustment = float(row["adjustment"])
    except (TypeError, ValueError):
        return ["non_numeric_amount"]
    if paid < 0:
        problems.append("negative_paid_amount")
    if not (SERVICE_WINDOW_START <= row["service_date"] <= SERVICE_WINDOW_END):
        problems.append("service_date_out_of_range")
    if row["diag_code"] not in DIAG_CODES:
        problems.append("unknown_diag_code")
    if abs(paid - (billed - adjustment)) > 0.01:
        problems.append("paid_amount_mismatch")
    return problems


def promote_to_silver(conn):
    """Bronze -> silver for all four feeds. Returns a stats dict.

    Members, labs and screenings pass through with a type check on age;
    claims get the full rule set: dedupe (latest copy of each claim_id
    wins, mirroring ROW_NUMBER() over the ingest order), then validation
    with every failing rule recorded and the row quarantined.
    """
    stats = {}
    members = conn.execute(
        "SELECT member_id, sex, age, plan, diabetes, hypertension,"
        " enrollment_start, enrollment_end FROM bronze_members").fetchall()
    member_ids = {m[0] for m in members}
    conn.execute("DELETE FROM silver_members")
    conn.executemany(
        "INSERT INTO silver_members"
        " (member_id, sex, age, plan, diabetes, hypertension,"
        " enrollment_start, enrollment_end)"
        " VALUES (?,?,?,?,?,?,?,?)", members)
    _log_delta(conn, "silver_members", "overwrite", len(members))
    stats["silver_members"] = len(members)

    for bronze, silver, cols in [
            ("bronze_labs", "silver_labs",
             "member_id, test, result, result_date"),
            ("bronze_screenings", "silver_screenings",
             "member_id, screening_type, screening_date")]:
        rows = conn.execute("SELECT %s FROM %s" % (cols, bronze)).fetchall()
        conn.execute("DELETE FROM %s" % silver)
        conn.executemany(
            "INSERT INTO %s (%s) VALUES (%s)"
            % (silver, cols, ", ".join("?" for _ in cols.split(", "))), rows)
        _log_delta(conn, silver, "overwrite", len(rows))
        stats[silver] = len(rows)

    raw_claims = conn.execute(
        "SELECT claim_id, member_id, service_date, diag_code,"
        " procedure_code, billed_amount, adjustment, paid_amount,"
        " source_file FROM bronze_claims ORDER BY rowid").fetchall()
    # Dedupe: latest copy of each claim_id wins.
    latest = {}
    for row in raw_claims:
        latest[row[0]] = row
    duplicates = len(raw_claims) - len(latest)

    conn.execute("DELETE FROM silver_claims")
    quarantined = 0
    clean = []
    for row in latest.values():
        record = dict(zip(
            ["claim_id", "member_id", "service_date", "diag_code",
             "procedure_code", "billed_amount", "adjustment",
             "paid_amount", "source_file"], row))
        problems = _claim_problems(record, member_ids)
        if problems:
            conn.execute(
                "INSERT INTO quarantine (source_table, record_id, reason,"
                " payload) VALUES (?, ?, ?, ?)",
                ("bronze_claims", record["claim_id"], ";".join(problems),
                 str(record)))
            quarantined += 1
        else:
            clean.append(row)
    conn.executemany(
        "INSERT INTO silver_claims"
        " (claim_id, member_id, service_date, diag_code, procedure_code,"
        " billed_amount, adjustment, paid_amount, source_file)"
        " VALUES (?,?,?,?,?,?,?,?,?)", clean)
    _log_delta(conn, "silver_claims", "overwrite", len(clean))
    stats["bronze_claims"] = len(raw_claims)
    stats["duplicates_removed"] = duplicates
    stats["silver_claims"] = len(clean)
    stats["quarantined"] = quarantined
    conn.commit()
    return stats


def reconcile(conn, month):
    """Check bronze = silver + quarantined + duplicates for the month.

    Returns (ok, detail). The numbers come from the recorded stats, not
    from re-reading the tables, so a mismatch means the load itself broke.
    """
    row = conn.execute(
        "SELECT bronze_claims, silver_claims, quarantined FROM run_stats"
        " WHERE measurement_month = ?", (month,)).fetchone()
    if row is None:
        return False, "no run_stats for %s" % month
    bronze, silver, quarantined = row
    dup_rows = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT claim_id) FROM bronze_claims"
    ).fetchone()[0]
    ok = bronze == silver + quarantined + dup_rows
    return ok, ("bronze=%d silver=%d quarantined=%d duplicates_removed=%d"
                % (bronze, silver, quarantined, dup_rows))


def save_run_stats(conn, month, stats):
    conn.execute(
        "INSERT OR REPLACE INTO run_stats"
        " (measurement_month, bronze_claims, silver_claims, quarantined)"
        " VALUES (?, ?, ?, ?)",
        (month, stats["bronze_claims"], stats["silver_claims"],
         stats["quarantined"]))
    conn.commit()
