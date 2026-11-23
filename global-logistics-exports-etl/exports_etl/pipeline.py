"""Pipeline orchestration: extract, validate, transform, load."""

from collections import Counter
from datetime import date

from . import fx, ingest, quality, warehouse


def run(manifest_path, rates_path, db_path, today=None):
    """Run one ETL load and return a run report dict."""
    today = today or date.today()
    rates = ingest.read_rates(rates_path)
    raw_rows = ingest.read_manifests(manifest_path)
    valid, quarantined = quality.split_valid(raw_rows, rates, today=today)
    converted = [fx.convert_row(row, rates) for row in valid]

    conn = warehouse.connect(db_path)
    try:
        loaded = warehouse.load_rows(conn, converted)
        total_usd = warehouse.total_value_usd(conn)
        watermark = warehouse.get_watermark(conn)
    finally:
        conn.close()

    reason_counts = Counter()
    for item in quarantined:
        for reason in item["reasons"]:
            reason_counts[reason] += 1

    return {
        "received": len(raw_rows),
        "loaded": loaded,
        "quarantined": len(quarantined),
        "quarantine_reasons": dict(reason_counts),
        "total_value_usd": total_usd,
        "watermark": watermark,
        "quarantined_ids": [item["row"]["shipment_id"] for item in quarantined],
    }


def quarantined_detail(quarantined):
    """Human-readable quarantine lines for a run report."""
    return [
        f"{item['row']['shipment_id'] or '(no id)'}: {', '.join(item['reasons'])}"
        for item in quarantined
    ]
