import pandas as pd
import pytest

from session_stream.governance import Catalog, TableDef


def _catalog():
    cat = Catalog()
    cat.register(TableDef("media", "gold", "fact_session",
                          ["session_id", "user_id", "title_id"],
                          pii_columns=["user_id"]))
    return cat


def test_register_and_full_name():
    cat = _catalog()
    assert "media.gold.fact_session" in cat.tables
    assert cat.tables["media.gold.fact_session"].owner == "data-platform"


def test_register_duplicate_raises():
    cat = _catalog()
    with pytest.raises(ValueError):
        cat.register(TableDef("media", "gold", "fact_session",
                              ["session_id"]))


def test_register_unknown_pii_column_raises():
    cat = Catalog()
    with pytest.raises(ValueError):
        cat.register(TableDef("media", "gold", "fact_session",
                              ["session_id"], pii_columns=["ssn"]))


def test_record_lineage_and_audit():
    cat = _catalog()
    entry = cat.record_lineage("media.bronze.raw", "media.gold.fact_session",
                               "cleanse -> sessionize")
    assert entry["source"] == "media.bronze.raw"
    assert len(cat.lineage) == 1
    assert len(cat.audit) >= 2  # register + lineage


def test_mask_pii_hashes_user_ids():
    cat = _catalog()
    df = pd.DataFrame({"session_id": ["s1", "s2"],
                       "user_id": ["u1", "u2"],
                       "title_id": ["title-001", "title-002"]})
    masked = cat.mask_pii(df, "media.gold.fact_session")
    assert (masked["user_id"] != df["user_id"]).all()
    assert (masked["session_id"] == df["session_id"]).all()
    assert (masked["title_id"] == df["title_id"]).all()
    # deterministic: same input hashes the same way
    assert cat.mask_pii(df, "media.gold.fact_session")["user_id"].equals(
        masked["user_id"])


def test_mask_pii_unregistered_table_raises():
    cat = Catalog()
    with pytest.raises(ValueError):
        cat.mask_pii(pd.DataFrame({"user_id": ["u1"]}), "media.gold.nope")
