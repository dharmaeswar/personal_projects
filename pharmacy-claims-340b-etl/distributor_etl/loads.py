"""Distributor load orchestration: ingest -> validate -> load -> reconcile.

Mirrors claims_etl/loads.py for the distributor feeds. Every load ends
with a reconciliation report (source rows vs loaded vs quarantined) so
a bad feed is visible instead of silently short.
"""

from . import ingest, validate, warehouse


def run_load(db_path, shipments_path, inventory_path, customers_path,
             mode="full"):
    """Run one distributor load; return the reconciliation dict."""
    shipments, parse_errors = ingest.parse_shipments(shipments_path)
    inventory = ingest.parse_inventory(inventory_path)
    customers = ingest.parse_customers(customers_path)
    valid, quarantined = validate.validate_batch(shipments, inventory,
                                                 customers)
    conn = warehouse.connect(db_path)
    warehouse.upsert_dimensions(conn, inventory, customers)
    if mode == "full":
        loaded = warehouse.load_full(conn, valid, 0)
        watermark = max((s["ship_date"] for s in valid), default=None)
        load_id = warehouse.log_load(conn, "full", len(shipments), loaded,
                                     len(quarantined), watermark)
    else:
        watermark = warehouse.latest_watermark(conn)
        load_id = warehouse.log_load(conn, "incremental", len(shipments),
                                     0, len(quarantined), watermark)
        loaded, new_watermark, skipped = warehouse.load_incremental(
            conn, valid, watermark, load_id)
        conn.execute("UPDATE load_log SET loaded_rows = ?, watermark = ?"
                     " WHERE load_id = ?",
                     (loaded, new_watermark, load_id))
        conn.commit()
        watermark = new_watermark
    conn.close()
    return {"mode": mode, "load_id": load_id,
            "source_rows": len(shipments), "loaded_rows": loaded,
            "quarantined_rows": len(quarantined),
            "skipped_rows": skipped if mode != "full" else 0,
            "watermark": watermark,
            "parse_errors": parse_errors,
            "quarantined": [{"shipment_id": q["shipment"]["shipment_id"],
                             "violations": q["violations"]}
                            for q in quarantined]}


def reconcile(report):
    """True when every source row is accounted for: loaded, quarantined,
    or skipped as already loaded (past the watermark on a re-run)."""
    return (report["loaded_rows"] + report["quarantined_rows"]
            + report.get("skipped_rows", 0) == report["source_rows"])
