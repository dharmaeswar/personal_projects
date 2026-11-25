"""Structural checks on the T-SQL scripts (SQL Server targets).

The scripts are not executed here — no SQL Server instance is involved —
but every object the Python pipeline mirrors must exist by name, so a
rename in one place cannot silently drift from the other.
"""

from pathlib import Path

SQL = Path(__file__).resolve().parent.parent / "claims_etl" / "sql"


def _read(name):
    return (SQL / name).read_text(encoding="utf-8")


def test_create_tables_defines_warehouse_objects():
    text = _read("01_create_tables.sql")
    for name in ("DimPatient", "DimDrug", "FactClaims", "LoadLog",
                 "Quarantine"):
        assert name in text, name


def test_load_procedure_covers_both_modes():
    text = _read("02_sp_load_claims.sql")
    assert "usp_LoadClaims" in text
    assert "'FULL'" in text and "'INCREMENTAL'" in text
    assert "TRUNCATE TABLE dbo.FactClaims" in text
    assert "FillDate > @Watermark" in text


def test_validation_procedure_covers_all_six_rules():
    text = _read("03_sp_validate_340b.sql")
    assert "usp_Validate340B" in text
    assert "dbo.Quarantine" in text
    for fragment in ("not 340B-eligible", "11-digit", "days-supply",
                     "quantity x unit price", "duplicate claim_id",
                     "no 340B TPA capture"):
        assert fragment in text, fragment


def test_reconcile_procedure_exists():
    text = _read("04_sp_reconcile.sql")
    assert "usp_ReconcileLoads" in text
    assert "Reconciled" in text
