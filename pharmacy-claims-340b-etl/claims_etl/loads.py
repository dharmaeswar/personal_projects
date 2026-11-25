"""Orchestration: ingest -> validate -> load -> reconcile.

One run covers a daily, weekly, or monthly refresh cycle: the mode
('full' or 'incremental') picks the load strategy, and the returned
report proves the load reconciles: source rows = loaded + quarantined
(+ rows skipped as already loaded, for incremental runs).
"""

from pathlib import Path

from . import ingest, validate, warehouse

PLACEHOLDER_LOAD_ID = -1


def run_load(source_dir, db_path, mode="incremental",
             claims_file="pharmacy_claims.csv"):
    source_dir = Path(source_dir)
    claims, malformed = ingest.parse_claims_csv(source_dir / claims_file)
    tpa, tpa_bad = ingest.parse_tpa_xml(source_dir / "tpa_340b.xml")
    eligibility = ingest.parse_eligibility_flat(
        source_dir / "eligibility.txt")
    pricing = ingest.parse_pricing_json(source_dir / "drug_pricing.json")

    valid, quarantined = validate.validate_batch(
        claims, eligibility, pricing, tpa)

    conn = warehouse.connect(db_path)
    warehouse.upsert_dimensions(conn, eligibility, pricing)
    if mode == "full":
        loaded = warehouse.load_full(conn, valid, PLACEHOLDER_LOAD_ID)
        watermark = max((c["fill_date"] for c in valid), default=None)
    else:
        watermark_before = warehouse.latest_watermark(conn)
        loaded, watermark = warehouse.load_incremental(
            conn, valid, watermark_before, PLACEHOLDER_LOAD_ID)
    load_id = warehouse.log_load(conn, mode, len(claims), loaded,
                                 len(quarantined), watermark)
    conn.execute("UPDATE fact_claims SET load_id = ?"
                 " WHERE load_id = ?", (load_id, PLACEHOLDER_LOAD_ID))
    conn.commit()

    report = {
        "mode": mode,
        "load_id": load_id,
        "source_rows": len(claims),
        "malformed_rows": len(malformed) + len(tpa_bad),
        "loaded_rows": loaded,
        "quarantined_rows": len(quarantined),
        "skipped_already_loaded": len(valid) - loaded,
        "watermark": watermark,
        "fact_rows": warehouse.fact_count(conn),
        "reconciled": (len(claims) == loaded + len(quarantined)
                       + (len(valid) - loaded)),
        "quarantine": [{"claim_id": q["claim"]["claim_id"],
                        "violations": q["violations"]}
                       for q in quarantined],
    }
    conn.close()
    return report
