"""Ingest: read export manifests and FX rates from CSV files.

Manifest columns: shipment_id, ship_date (YYYY-MM-DD), origin, dest_country
(ISO 3166-1 alpha-2), hs_code, value, currency (ISO 4217), weight_kg,
customs_status. FX rates file columns: currency, rate_to_usd.
"""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation


def _parse_date(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        year, month, day = (int(part) for part in text.split("-"))
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _parse_decimal(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def read_manifests(path):
    """Read an export manifest CSV into a list of row dicts.

    Numeric/date fields are parsed when possible; unparseable values stay as
    ``None`` so the quality rules can quarantine the row with a reason.
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                {
                    "shipment_id": (raw.get("shipment_id") or "").strip(),
                    "ship_date": _parse_date(raw.get("ship_date")),
                    "ship_date_raw": (raw.get("ship_date") or "").strip(),
                    "origin": (raw.get("origin") or "").strip(),
                    "dest_country": (raw.get("dest_country") or "").strip().upper(),
                    "hs_code": (raw.get("hs_code") or "").strip(),
                    "value": _parse_decimal(raw.get("value")),
                    "value_raw": (raw.get("value") or "").strip(),
                    "currency": (raw.get("currency") or "").strip().upper(),
                    "weight_kg": _parse_decimal(raw.get("weight_kg")),
                    "customs_status": (raw.get("customs_status") or "").strip().upper(),
                }
            )
    return rows


def read_rates(path):
    """Read an FX rates CSV into {currency: Decimal rate_to_usd}."""
    rates = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            currency = (raw.get("currency") or "").strip().upper()
            rate = _parse_decimal(raw.get("rate_to_usd"))
            if currency and rate is not None and rate > 0:
                rates[currency] = rate
    return rates
