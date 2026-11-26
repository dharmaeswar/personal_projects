"""Tests for the Power BI semantic-model export and the SQL files."""

import re
from pathlib import Path

from fabric_hedis.powerbi import build_semantic_model

SQL_DIR = Path(__file__).resolve().parent.parent / "fabric_hedis" / "sql"


def test_measures_reference_real_tables_and_columns():
    model = build_semantic_model()
    tables = {t["name"]: set(t["columns"]) for t in model["tables"]}
    for measure in model["measures"]:
        for table, column in re.findall(r"(\w+)\[(\w+)\]", measure["dax"]):
            assert table in tables, measure["name"]
            assert column in tables[table], measure["name"]


def test_relationships_and_rls_reference_real_tables():
    model = build_semantic_model()
    tables = {t["name"] for t in model["tables"]}
    for rel in model["relationships"]:
        assert rel["from"].split("[")[0] in tables
        assert rel["to"].split("[")[0] in tables
    for role in model["roles"]:
        assert role["table"] in tables
        assert role["filter"].split("[")[0] == role["table"]


def test_model_covers_all_four_hedis_measures():
    model = build_semantic_model()
    dax = " ".join(m["dax"] for m in model["measures"])
    for measure in ("BCS", "COL", "CDC", "CBP"):
        assert measure in dax


def test_sql_files_present_and_structured():
    ddl = (SQL_DIR / "warehouse_ddl.sql").read_text()
    assert "CREATE TABLE dbo.bronze_claims" in ddl
    assert "CREATE TABLE dbo.gold_hedis_monthly" in ddl
    assert "IX_silver_claims_service_date" in ddl
    load = (SQL_DIR / "sp_load_silver.sql").read_text()
    assert "CREATE OR ALTER PROCEDURE dbo.sp_load_silver_claims" in load
    assert "ROW_NUMBER() OVER (PARTITION BY claim_id" in load
    assert "MERGE INTO dbo.silver_claims" in load
    hedis = (SQL_DIR / "sp_compute_hedis_monthly.sql").read_text()
    assert "CREATE OR ALTER PROCEDURE dbo.sp_compute_hedis_monthly" in hedis
    for measure in ("'BCS'", "'COL'", "'CDC'", "'CBP'"):
        assert measure in hedis
    fn = (SQL_DIR / "fn_hedis_eligible.sql").read_text()
    assert "CREATE OR ALTER FUNCTION dbo.fn_hedis_eligible" in fn
    assert "RETURNS BIT" in fn
