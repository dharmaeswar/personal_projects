"""Tests for the forward-deployed governed data-integration toolkit."""

import sqlite3

import pytest

from afe_data.contracts import DataContract
from afe_data.governance import AccessControl, LineageLog, LineageEntry, classify_column, mask_value
from afe_data.pipeline import PodPipeline
from afe_data.quality import check_rows, detect_schema_drift
from afe_data.retrieval import RetrievalIndex, feature_snapshot
from afe_data.sources import (
    OracleExtractAdapter,
    PostgresDumpAdapter,
    RestApiAdapter,
    SourceProfile,
)
from afe_data.transform import transform_row


def _contract():
    return DataContract(
        dataset="client-positions",
        expected_columns=["position_id", "client_id", "instrument", "notional",
                          "currency", "valuation_date", "tax_id"],
        required_columns=["position_id", "client_id", "instrument", "notional"],
        freshness_hours=24,
        completeness_floor=0.6,
    )


PG_V2 = """position_id,client_id,instrument,notional,currency,valuation_date,tax_id
P-1,ACME,IRS-SWAP-5Y,2500000,USD,2026-11-20,***-1
P-2,ACME,CDS-IG-3Y,1200000,USD,2026-11-20,***-2
"""


# --- sources ---

def test_postgres_adapter_reads_csv_and_tags_schema_version():
    adapter = PostgresDumpAdapter(SourceProfile("client-postgres", "Postgres", "on-prem", "ops"), PG_V2, "v2")
    rows = adapter.read()
    assert len(rows) == 2
    assert rows[0].source == "client-postgres"
    assert rows[0].schema_version == "v2"
    assert rows[0].payload["instrument"] == "IRS-SWAP-5Y"
    assert "position_id" in adapter.schema_seen


def test_oracle_adapter_reads_pipe_delimited_extract():
    text = "RISK_ID|CLIENT|INSTRUMENT|NOTIONAL|CCY|VAL_DT\nR-1|ACME|IRS-SWAP-5Y|100|USD|2026-11-20\n"
    adapter = OracleExtractAdapter(SourceProfile("risk-oracle", "Oracle", "on-prem", "risk"), text, "v1")
    rows = adapter.read()
    assert len(rows) == 1
    assert rows[0].payload["CLIENT"] == "ACME"
    assert rows[0].record_id == "R-1"


def test_rest_api_adapter_retries_transient_failure_once():
    pages = [[{"client_id": "ACME"}], [{"client_id": "GLOBEX"}]]
    adapter = RestApiAdapter(SourceProfile("api", "REST API", "cloud", "master"), pages, fail_page=1)
    rows = adapter.read()
    assert len(rows) == 2
    assert adapter.retries_used == 1


# --- contracts ---

def test_contract_rejects_missing_required_column():
    violations = _contract().check_schema(["client_id", "instrument"])
    assert any(v.kind == "breaking-schema" for v in violations)


def test_contract_accepts_additive_column():
    violations = _contract().check_schema(
        ["position_id", "client_id", "instrument", "notional", "currency", "valuation_date", "tax_id", "new_col"])
    assert violations == []


def test_contract_flags_stale_data():
    assert _contract().check_freshness(30.0)  # SLA is 24h
    assert _contract().check_freshness(2.0) == []


def test_contract_flags_low_completeness():
    rows = [{"position_id": "P-1", "client_id": "ACME", "instrument": "X", "notional": 1},
            {"position_id": None, "client_id": "ACME", "instrument": "X", "notional": None}]
    assert _contract().check_completeness(rows)  # 0.5 < 0.6 floor


# --- transform ---

def test_transform_maps_v1_and_v2_field_names():
    row_v1, _ = transform_row("client-postgres", {"pos_id": "P-9", "client": "ACME",
                                                 "ticker": "IRS", "notional_usd": "100",
                                                 "ccy": "USD", "val_date": "2026-11-20"})
    assert row_v1["position_id"] == "P-9" and row_v1["instrument"] == "IRS"
    assert row_v1["notional"] == 100.0
    row_v2, _ = transform_row("client-postgres", {"position_id": "P-9", "client_id": "ACME",
                                                 "instrument": "IRS", "notional": "100",
                                                 "currency": "USD", "valuation_date": "2026-11-20"})
    assert row_v2["position_id"] == "P-9" and row_v2["currency"] == "USD"


def test_transform_reports_unmapped_columns():
    _, unmapped = transform_row("client-postgres", {"position_id": "P-1", "tax_id": "***-1"})
    assert "tax_id" in unmapped  # restricted identifier is excluded from the canonical model


# --- quality & drift ---

def test_quality_quarantines_missing_duplicate_and_bad_rows():
    rows = [
        {"position_id": "P-1", "client_id": "ACME", "instrument": "IRS", "notional": 100},
        {"position_id": "P-2", "client_id": "ACME", "instrument": "IRS", "notional": None},
        {"position_id": "P-1", "client_id": "ACME", "instrument": "IRS", "notional": 100},
        {"position_id": "P-3", "client_id": "ACME", "instrument": "IRS", "notional": -999999999},
        {"position_id": "P-4", "client_id": "NOBODY", "instrument": "IRS", "notional": 100},
    ]
    report = check_rows(rows, ["position_id", "client_id", "instrument", "notional"],
                        {"notional": (-10_000_000, 10_000_000)}, "position_id", {"ACME"})
    assert report.passed == ["P-1"]
    assert report.quarantined_count == 4
    reasons = " ".join(q.reason for q in report.quarantined)
    assert "missing notional" in reasons and "duplicate" in reasons
    assert "outside" in reasons and "unknown client_id" in reasons


def test_schema_drift_added_is_not_blocking_removed_is_blocking():
    events = detect_schema_drift("src", ["a", "b"], ["a", "b", "c"])
    assert len(events) == 1 and events[0].kind == "added" and not events[0].blocking
    events = detect_schema_drift("src", ["a", "b"], ["a"])
    assert len(events) == 1 and events[0].kind == "removed" and events[0].blocking


# --- governance ---

def test_classify_flags_pii_columns():
    assert classify_column("tax_id", ["***-1"]) == "restricted"
    assert classify_column("email", ["a@b.com"]) == "restricted"
    assert classify_column("instrument", ["IRS-SWAP"]) == "internal"


def test_masking_methods():
    assert mask_value("secret") == "***"
    assert mask_value("123456789", "last4") == "****6789"
    assert len(mask_value("secret", "hash")) == 12


def test_access_control_masks_restricted_for_analyst_but_not_auditor():
    ac = AccessControl()
    row = {"instrument": "IRS", "tax_id": "***-1"}
    sensitivities = {"instrument": "internal", "tax_id": "restricted"}
    analyst = ac.read_row("analyst", row, sensitivities, "analytics")
    assert analyst["tax_id"] == "***" and analyst["instrument"] == "IRS"
    auditor = ac.read_row("auditor", row, sensitivities, "audit")
    assert auditor["tax_id"] == "***-1"
    assert any(not e.allowed for e in ac.log)


def test_model_training_blocked_on_restricted_data():
    ac = AccessControl()
    assert ac.can_read("pod-admin", "restricted", "model-training") is False


def test_lineage_traces_a_row_to_its_source():
    log = LineageLog()
    log.record(LineageEntry("P-1", "client-postgres", "v2", "transform_row v1", "contract v1"))
    traced = log.trace("P-1")
    assert len(traced) == 1 and traced[0].source == "client-postgres"


# --- retrieval ---

def test_retrieval_ranks_relevant_doc_first():
    index = RetrievalIndex()
    index.add("d1", "IRS swap position ACME notional 2500000 USD", "internal")
    index.add("d2", "FX forward EURUSD Globex currency hedge", "internal")
    hits = index.search("IRS swap ACME", top_k=1)
    assert hits[0].doc_id == "d1" and hits[0].score > 0


def test_feature_snapshot_buckets_large_notionals():
    snap = feature_snapshot({"position_id": "P-1", "client_id": "ACME", "instrument": "IRS",
                             "notional": 2500000, "currency": "USD", "valuation_date": "2026-11-20"})
    assert snap["notional_bucket"] == "large"
    assert snap["as_of"] == "2026-11-20"


# --- pipeline end to end ---

def test_pipeline_loads_clean_rows_and_quarantines_bad_ones(tmp_path):
    pipe = PodPipeline(tmp_path / "test.db")
    adapter = PostgresDumpAdapter(
        SourceProfile("client-postgres", "Postgres", "on-prem", "ops"), PG_V2, "v2")
    result = pipe.run(adapter, _contract(), {"ACME"}, ["position_id", "client_id",
                      "instrument", "notional", "currency", "valuation_date"])
    assert result["loaded"] == 2 and result["quarantined"] == 0 and not result["blocked"]
    assert len(pipe.lineage.entries) == 2


def test_pipeline_blocks_on_contract_violation(tmp_path):
    pipe = PodPipeline(tmp_path / "test.db")
    adapter = PostgresDumpAdapter(
        SourceProfile("client-postgres", "Postgres", "on-prem", "ops"),
        "client_id,instrument,notional\nACME,IRS,100\n", "v2")
    result = pipe.run(adapter, _contract(), {"ACME"}, ["client_id", "instrument", "notional"])
    assert result["blocked"] and result["loaded"] == 0


def test_pipeline_rerun_is_idempotent(tmp_path):
    pipe = PodPipeline(tmp_path / "test.db")
    adapter = PostgresDumpAdapter(
        SourceProfile("client-postgres", "Postgres", "on-prem", "ops"), PG_V2, "v2")
    first = pipe.run(adapter, _contract(), {"ACME"}, ["position_id", "client_id",
                     "instrument", "notional", "currency", "valuation_date"])
    second = pipe.run(adapter, _contract(), {"ACME"}, ["position_id", "client_id",
                      "instrument", "notional", "currency", "valuation_date"])
    assert first["loaded"] == 2 and second["loaded"] == 0
    with sqlite3.connect(tmp_path / "test.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 2


def test_pipeline_quarantines_bad_rows_and_still_loads_good_ones(tmp_path):
    bad_csv = """position_id,client_id,instrument,notional,currency,valuation_date
P-1,ACME,IRS,100,USD,2026-11-20
P-2,ACME,IRS,,USD,2026-11-20
P-1,ACME,IRS,100,USD,2026-11-20
"""
    pipe = PodPipeline(tmp_path / "test.db")
    adapter = PostgresDumpAdapter(
        SourceProfile("client-postgres", "Postgres", "on-prem", "ops"), bad_csv, "v2")
    result = pipe.run(adapter, _contract(), {"ACME"}, ["position_id", "client_id",
                      "instrument", "notional", "currency", "valuation_date"])
    assert result["loaded"] == 1 and result["quarantined"] == 2
    assert len(pipe.feature_store_snapshot()) == 1
