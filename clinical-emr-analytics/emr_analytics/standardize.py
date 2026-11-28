"""Standardize EMR rows to one common vocabulary.

This is the data-standardization step the HCA role describes: disparate
source feeds use different names, units, and spellings for the same
clinical concept. Standardization maps them to canonical names and
canonical units before any quality rule or measure runs, so a value is
never judged against a range expressed in the wrong unit.

Canonical forms:
- Vitals: TEMP_F -> TEMP_C (value converted); HEART_RATE in bpm,
  BP_SYSTOLIC / BP_DIASTOLIC in mmHg, SPO2 in %.
- Labs: test-name aliases (HGB, A1C, LDL) -> canonical test names.
- Medications: dose converted to milligrams where the unit allows it
  (mcg -> mg, g -> mg); "units" doses keep dose_mg as None because a
  unit is not a mass.
"""

# Plausible clinical ranges, expressed in CANONICAL units.
VITAL_RANGES = {
    "HEART_RATE": (30.0, 200.0),      # bpm
    "BP_SYSTOLIC": (70.0, 250.0),     # mmHg
    "BP_DIASTOLIC": (40.0, 150.0),    # mmHg
    "SPO2": (70.0, 100.0),            # %
    "TEMP_C": (35.0, 41.5),            # deg C
}

LAB_RANGES = {
    "HbA1c": (3.0, 15.0),             # %
    "LDL Cholesterol": (30.0, 400.0),  # mg/dL
    "Creatinine": (0.3, 8.0),         # mg/dL
    "Hemoglobin": (5.0, 20.0),        # g/dL
    "Sodium": (120.0, 160.0),         # mmol/L
}

LAB_CANONICAL = {
    "HGB": "Hemoglobin",
    "Hgb": "Hemoglobin",
    "A1C": "HbA1c",
    "HbA1c": "HbA1c",
    "LDL": "LDL Cholesterol",
    "LDL Cholesterol": "LDL Cholesterol",
    "Creatinine": "Creatinine",
    "Hemoglobin": "Hemoglobin",
    "Sodium": "Sodium",
}

# dose unit -> milligrams per unit; None means "no mass conversion".
DOSE_TO_MG = {
    "mg": 1.0,
    "mcg": 0.001,
    "g": 1000.0,
    "units": None,
    "mL": None,
}

KNOWN_DOSE_UNITS = set(DOSE_TO_MG)


def to_float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def standardize_vital(row):
    """Return (row, notes). Converts TEMP_F to TEMP_C; everything else
    keeps its value and canonical unit."""
    out = dict(row)
    notes = []
    if row.get("vital_type") == "TEMP_F":
        value = to_float(row.get("value"))
        if value is not None:
            out["value"] = "%.2f" % ((value - 32.0) * 5.0 / 9.0)
        out["vital_type"] = "TEMP_C"
        out["unit"] = "C"
        notes.append("TEMP_F converted to TEMP_C")
    return out, notes


def standardize_lab(row):
    """Return (row, notes). Maps test-name aliases to canonical names."""
    out = dict(row)
    notes = []
    canonical = LAB_CANONICAL.get(row.get("test_name", "").strip())
    if canonical is None:
        notes.append("unknown test name %r kept as-is"
                     % row.get("test_name", ""))
    else:
        if canonical != row.get("test_name"):
            notes.append("test %r mapped to %r"
                         % (row.get("test_name"), canonical))
        out["test_name"] = canonical
    return out, notes


def standardize_medication(row):
    """Return (row, notes). Adds dose_mg where the unit converts to mass."""
    out = dict(row)
    notes = []
    unit = (row.get("dose_unit") or "").strip()
    dose = to_float(row.get("dose"))
    if unit in DOSE_TO_MG and DOSE_TO_MG[unit] is not None and dose is not None:
        out["dose_mg"] = "%.4f" % (dose * DOSE_TO_MG[unit])
        if unit != "mg":
            notes.append("dose %s %s converted to %s mg"
                         % (row.get("dose"), unit, out["dose_mg"]))
    else:
        out["dose_mg"] = ""
        if unit not in DOSE_TO_MG:
            notes.append("unknown dose unit %r" % unit)
    return out, notes


def standardize_feeds(feeds):
    """Standardize every feed. Returns (standardized, notes) where notes
    maps feed name -> list of (row id, note) pairs."""
    out = {"encounters": [dict(r) for r in feeds.get("encounters", [])]}
    notes = {}
    for feed, fn in (("vitals", standardize_vital),
                     ("labs", standardize_lab),
                     ("medications", standardize_medication)):
        rows, feed_notes = [], []
        id_field = {"vitals": "vital_id", "labs": "lab_id",
                    "medications": "med_id"}[feed]
        for row in feeds.get(feed, []):
            std, row_notes = fn(row)
            rows.append(std)
            for note in row_notes:
                feed_notes.append((row.get(id_field), note))
        out[feed] = rows
        notes[feed] = feed_notes
    return out, notes
