"""Data-quality rules for export manifests.

Every rule returns a reason code; a row with any reason is quarantined and
never loaded. Rules mirror the checks a Global Logistics data team runs
before a manifest reaches the warehouse.
"""

import re
from datetime import date

HS_CODE_RE = re.compile(r"^\d{4}(\.\d{2}){0,2}$")
VALID_STATUSES = {"CLEARED", "IN_TRANSIT", "HELD", "DELIVERED"}


def validate_row(row, seen_ids, rates, today=None):
    """Return a list of quarantine reason codes for one manifest row.

    ``seen_ids`` tracks shipment ids already accepted in this run (duplicates
    are quarantined). ``rates`` is the FX table; unknown currencies fail.
    ``today`` defaults to the current date and bounds future ship dates.
    """
    reasons = []
    today = today or date.today()

    shipment_id = row.get("shipment_id") or ""
    if not shipment_id:
        reasons.append("missing_shipment_id")
    elif shipment_id in seen_ids:
        reasons.append("duplicate_shipment_id")

    if row.get("ship_date") is None:
        reasons.append("bad_ship_date")
    elif row["ship_date"] > today:
        reasons.append("future_ship_date")

    if not row.get("dest_country"):
        reasons.append("missing_dest_country")

    hs_code = row.get("hs_code") or ""
    if not hs_code:
        reasons.append("missing_hs_code")
    elif not HS_CODE_RE.match(hs_code):
        reasons.append("bad_hs_code")

    value = row.get("value")
    if value is None:
        reasons.append("bad_value")
    elif value <= 0:
        reasons.append("non_positive_value")

    currency = row.get("currency") or ""
    if not currency:
        reasons.append("missing_currency")
    elif currency not in rates:
        reasons.append("unknown_currency")

    weight = row.get("weight_kg")
    if weight is None:
        reasons.append("bad_weight")
    elif weight <= 0:
        reasons.append("non_positive_weight")

    if (row.get("customs_status") or "") not in VALID_STATUSES:
        reasons.append("bad_customs_status")

    return reasons


def split_valid(rows, rates, today=None):
    """Split manifest rows into (valid, quarantined) lists.

    ``quarantined`` entries are ``{"row": row, "reasons": [...]}`` dicts.
    Duplicate detection uses ids accepted earlier in the same run only.
    """
    valid = []
    quarantined = []
    seen_ids = set()
    for row in rows:
        reasons = validate_row(row, seen_ids, rates, today=today)
        if reasons:
            quarantined.append({"row": row, "reasons": reasons})
        else:
            seen_ids.add(row["shipment_id"])
            valid.append(row)
    return valid, quarantined
