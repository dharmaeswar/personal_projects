"""Data quality: validation, quarantine, reconciliation, observability.

Every mapped row is checked before load. A row that fails any check is
quarantined with a reason — never silently loaded and never silently
dropped. Reconciliation then proves the load: source row counts and
price totals must match the warehouse after loading. The run report is
the observability surface: counts of missing, duplicated, delayed and
inconsistent rows per source.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NATURAL_KEY = ("competitor", "zone", "snapshot_date", "service")


@dataclass
class QualityReport:
    checked: int
    loaded: int
    quarantined: list  # (row, reason)
    duplicates: int
    missing: int
    delayed: int
    inconsistent: int

    def to_dict(self):
        return {
            "checked": self.checked,
            "loaded": self.loaded,
            "quarantined": len(self.quarantined),
            "duplicates": self.duplicates,
            "missing": self.missing,
            "delayed": self.delayed,
            "inconsistent": self.inconsistent,
            "quarantine_reasons": [reason for _, reason in self.quarantined],
        }


def run_quality_checks(rows, watermark_date=None, known_zones=None):
    """Check mapped rows. `watermark_date` (ISO date): rows dated before
    it are late-arriving and counted as delayed, but still loaded —
    late data is valid data. `known_zones`: rows for unknown zones are
    inconsistent and quarantined."""
    seen = set()
    quarantined = []
    loaded_rows = []
    duplicates = missing = delayed = inconsistent = 0
    for row in rows:
        key = tuple(row.get(k) for k in NATURAL_KEY)
        if any(v in (None, "") for v in (row.get(k) for k in ("competitor", "zone", "snapshot_date", "price_usd"))):
            missing += 1
            quarantined.append((row, "missing required field"))
            continue
        if key in seen:
            duplicates += 1
            quarantined.append((row, "duplicate natural key"))
            continue
        seen.add(key)
        price = row.get("price_usd")
        try:
            price_num = None if price is None else float(price)
        except (TypeError, ValueError):
            inconsistent += 1
            quarantined.append((row, f"price_usd not numeric: {price!r}"))
            continue
        if price_num is not None and price_num <= 0:
            inconsistent += 1
            quarantined.append((row, "price_usd <= 0"))
            continue
        if known_zones is not None and row.get("zone") not in known_zones:
            inconsistent += 1
            quarantined.append((row, f"unknown zone: {row.get('zone')}"))
            continue
        if watermark_date and row.get("snapshot_date", "") < watermark_date:
            delayed += 1
        loaded_rows.append(row)
    return loaded_rows, QualityReport(
        checked=len(rows),
        loaded=len(loaded_rows),
        quarantined=quarantined,
        duplicates=duplicates,
        missing=missing,
        delayed=delayed,
        inconsistent=inconsistent,
    )


@dataclass
class Reconciliation:
    source_rows: int
    warehouse_rows: int
    source_price_total: float
    warehouse_price_total: float

    @property
    def rows_match(self):
        return self.source_rows == self.warehouse_rows

    @property
    def totals_match(self):
        return abs(self.source_price_total - self.warehouse_price_total) < 0.01

    @property
    def ok(self):
        return self.rows_match and self.totals_match

    def to_dict(self):
        return {
            "source_rows": self.source_rows,
            "warehouse_rows": self.warehouse_rows,
            "source_price_total": round(self.source_price_total, 2),
            "warehouse_price_total": round(self.warehouse_price_total, 2),
            "rows_match": self.rows_match,
            "totals_match": self.totals_match,
        }


def reconcile(loaded_rows, warehouse_rows, warehouse_price_total):
    return Reconciliation(
        source_rows=len(loaded_rows),
        warehouse_rows=warehouse_rows,
        source_price_total=round(
            sum(r.get("price_usd") or 0 for r in loaded_rows), 2
        ),
        warehouse_price_total=round(warehouse_price_total, 2),
    )
