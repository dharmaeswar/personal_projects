"""Structural tests for the Snowflake SQL scripts.

The scripts are not executed against Snowflake here; these checks catch
the common mistakes that would break them there: SQLite-isms, missing
tables, a MERGE without a key, or a reconciliation query without its
three checks.
"""

from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "homehealth" / "sql"

FORBIDDEN = ("ON CONFLICT", "INSERT OR IGNORE", "INTEGER PRIMARY KEY AUTOINCREMENT")


def read(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def test_all_sql_files_exist():
    assert {p.name for p in SQL_DIR.glob("*.sql")} == {
        "01_create_tables.sql",
        "02_load_visits.sql",
        "03_reconcile.sql",
    }


def test_no_sqlite_syntax_in_snowflake_scripts():
    for name in ("01_create_tables.sql", "02_load_visits.sql", "03_reconcile.sql"):
        text = read(name)
        for bad in FORBIDDEN:
            assert bad not in text, f"{name} contains SQLite-ism {bad!r}"


def test_ddl_creates_all_tables():
    ddl = read("01_create_tables.sql")
    for table in (
        "DIM_PATIENT", "DIM_CLINICIAN", "DIM_DATE",
        "FACT_HOME_VISIT", "LOAD_LOG", "QUARANTINE", "WATERMARK",
    ):
        assert table in ddl


def test_load_script_is_keyed_merge():
    load = read("02_load_visits.sql")
    assert "MERGE INTO WH.FACT_HOME_VISIT" in load
    assert "ON T.VISIT_ID = S.VISIT_ID" in load
    assert "WHEN NOT MATCHED THEN INSERT" in load
    assert "WATERMARK" in load


def test_reconcile_script_has_three_checks():
    rec = read("03_reconcile.sql")
    assert "source_vs_loaded_quarantined" in rec
    assert "fact_to_non_current_patient" in rec
    assert "duplicate_visit_ids" in rec
