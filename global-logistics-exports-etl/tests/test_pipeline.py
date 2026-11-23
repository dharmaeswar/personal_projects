import os

from exports_etl import pipeline

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_sample_run_loads_17_quarantines_3(tmp_path):
    report = pipeline.run(
        os.path.join(HERE, "data", "sample_manifests.csv"),
        os.path.join(HERE, "data", "fx_rates.csv"),
        str(tmp_path / "exports.db"),
    )
    assert report["received"] == 20
    assert report["loaded"] == 17
    assert report["quarantined"] == 3
    assert report["quarantine_reasons"] == {
        "duplicate_shipment_id": 1,
        "non_positive_value": 1,
        "unknown_currency": 1,
    }
    assert set(report["quarantined_ids"]) == {"EXP-0001", "EXP-0018", "EXP-0019"}
    assert report["watermark"] == "2026-11-12"
    assert report["total_value_usd"] > 0


def test_sample_run_is_idempotent(tmp_path):
    db = str(tmp_path / "exports.db")
    manifest = os.path.join(HERE, "data", "sample_manifests.csv")
    rates = os.path.join(HERE, "data", "fx_rates.csv")
    first = pipeline.run(manifest, rates, db)
    second = pipeline.run(manifest, rates, db)
    assert first["loaded"] == 17
    assert second["loaded"] == 0  # nothing new on re-run
    assert second["total_value_usd"] == first["total_value_usd"]


def test_empty_manifest_loads_nothing(tmp_path):
    manifest = tmp_path / "empty.csv"
    manifest.write_text(
        "shipment_id,ship_date,origin,dest_country,hs_code,value,currency,weight_kg,customs_status\n"
    )
    rates = tmp_path / "rates.csv"
    rates.write_text("currency,rate_to_usd\nUSD,1.00\n")
    report = pipeline.run(str(manifest), str(rates), str(tmp_path / "e.db"))
    assert report == {
        "received": 0,
        "loaded": 0,
        "quarantined": 0,
        "quarantine_reasons": {},
        "total_value_usd": 0.0,
        "watermark": None,
        "quarantined_ids": [],
    }


def test_all_bad_manifest_loads_nothing(tmp_path):
    manifest = tmp_path / "bad.csv"
    manifest.write_text(
        "shipment_id,ship_date,origin,dest_country,hs_code,value,currency,weight_kg,customs_status\n"
        "EXP-1,2026-11-02,US,DE,8471.30,-5,USD,10,CLEARED\n"
    )
    rates = tmp_path / "rates.csv"
    rates.write_text("currency,rate_to_usd\nUSD,1.00\n")
    report = pipeline.run(str(manifest), str(rates), str(tmp_path / "e.db"))
    assert report["loaded"] == 0
    assert report["quarantined"] == 1
    assert report["quarantine_reasons"] == {"non_positive_value": 1}
