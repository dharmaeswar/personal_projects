"""Load the synthetic EMR feeds (CSV) into row dicts.

Each feed is a CSV in ``data/``: encounters, vitals, labs, medications.
Rows that do not match the header (wrong field count, empty id) are
reported as malformed and skipped — never silently dropped.
"""

import csv
import os

FEEDS = {
    "encounters": "encounters.csv",
    "vitals": "vitals.csv",
    "labs": "labs.csv",
    "medications": "medications.csv",
}

REQUIRED_ID = {
    "encounters": "encounter_id",
    "vitals": "vital_id",
    "labs": "lab_id",
    "medications": "med_id",
}


def load_csv(path):
    """Return (rows, malformed) for one CSV file.

    ``malformed`` is a list of {"line": n, "reason": str, "raw": [...]}.
    """
    rows = []
    malformed = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        for n, row in enumerate(reader, start=2):
            if None in row or any(v is None for v in row.values()):
                malformed.append({
                    "line": n,
                    "reason": "wrong number of fields for header",
                    "raw": [row.get(h) for h in header],
                })
                continue
            id_field = REQUIRED_ID.get(os.path.basename(path).replace(".csv", ""))
            if id_field and not (row.get(id_field) or "").strip():
                malformed.append({
                    "line": n,
                    "reason": "missing %s" % id_field,
                    "raw": [row.get(h) for h in header],
                })
                continue
            rows.append({k: (v.strip() if isinstance(v, str) else v)
                         for k, v in row.items()})
    return rows, malformed


def load_feeds(data_dir):
    """Load every feed. Returns (feeds, malformed) where feeds maps
    feed name -> list of row dicts and malformed maps feed name ->
    list of malformed-row reports."""
    feeds = {}
    malformed = {}
    for name, filename in FEEDS.items():
        rows, bad = load_csv(os.path.join(data_dir, filename))
        feeds[name] = rows
        if bad:
            malformed[name] = bad
    return feeds, malformed
