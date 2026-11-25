"""Transformation into the canonical governed model.

Source-specific field names are mapped onto one canonical schema so the AI
system sees the same shape whatever legacy system a record came from.
Mapping is explicit and versioned: a rename in a source (v1 `pos_id` ->
v2 `position_id`) is handled by the map, and unmapped columns are reported
instead of silently dropped.
"""

from __future__ import annotations


CANONICAL_COLUMNS = [
    "position_id",
    "client_id",
    "instrument",
    "notional",
    "currency",
    "valuation_date",
]

# source column -> canonical column, per source system
FIELD_MAPS = {
    "client-postgres": {
        "position_id": "position_id",
        "pos_id": "position_id",  # v1 name for the same field
        "client": "client_id",
        "client_id": "client_id",
        "instrument": "instrument",
        "ticker": "instrument",
        "notional": "notional",
        "notional_usd": "notional",
        "ccy": "currency",
        "currency": "currency",
        "val_date": "valuation_date",
        "valuation_date": "valuation_date",
    },
    "risk-oracle": {
        "RISK_ID": "position_id",
        "CLIENT": "client_id",
        "INSTRUMENT": "instrument",
        "NOTIONAL": "notional",
        "CCY": "currency",
        "VAL_DT": "valuation_date",
    },
}


def transform_row(source: str, payload: dict) -> tuple[dict, list[str]]:
    """Map one raw payload onto the canonical schema.

    Returns (canonical_row, unmapped_columns). Unmapped columns are
    reported so a schema change is visible instead of silently lost.
    """
    field_map = FIELD_MAPS.get(source, {})
    canonical: dict = {}
    unmapped: list[str] = []
    for key, value in payload.items():
        target = field_map.get(key)
        if target is None:
            unmapped.append(key)
            continue
        canonical[target] = value
    for col in CANONICAL_COLUMNS:
        canonical.setdefault(col, None)
    # normalise notional to a float where possible; leave the raw value for
    # the quality layer to flag if it is not numeric
    if canonical["notional"] is not None:
        try:
            canonical["notional"] = float(canonical["notional"])
        except (TypeError, ValueError):
            pass
    return canonical, unmapped
