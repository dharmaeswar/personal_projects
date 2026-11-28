"""Clinical quality measures over clean EMR data.

Every measure is a documented denominator/numerator pair computed only
from rows that passed the data-quality rules. Definitions:

- vitals_completeness_pct: encounters with a clean heart rate, systolic
  blood pressure, and SpO2 recorded, over all encounters.
- lab_turnaround_median_hours: median hours from lab collection to
  result, over clean labs.
- med_reconciliation_pct: encounters with at least one clean medication
  recorded, over all encounters.
- data_quality_pass_rate_pct: rows passing all quality rules, over all
  rows loaded across the four feeds.
- return_visit_rate_pct: patients with two encounters within 30 days,
  over all patients (a return-visit proxy, not a clinical readmission
  rate — the data has no admission/discharge linkage to prove that).
"""

from datetime import datetime

from .standardize import to_float


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _hours_between(start, end):
    fmt = "%Y-%m-%dT%H:%M"
    try:
        return (datetime.strptime(end, fmt)
                - datetime.strptime(start, fmt)).total_seconds() / 3600.0
    except (TypeError, ValueError):
        return None


def compute_measures(clean, quarantined, total_rows):
    encounters = clean.get("encounters", [])
    vitals = clean.get("vitals", [])
    labs = clean.get("labs", [])
    meds = clean.get("medications", [])

    encounter_ids = [e["encounter_id"] for e in encounters]

    # Vitals completeness: HR + BP_SYSTOLIC + SPO2 present per encounter.
    core = {"HEART_RATE", "BP_SYSTOLIC", "SPO2"}
    have = {}
    for v in vitals:
        have.setdefault(v["encounter_id"], set()).add(v["vital_type"])
    complete = sum(1 for eid in encounter_ids
                   if core <= have.get(eid, set()))
    vitals_completeness = (100.0 * complete / len(encounter_ids)
                           if encounter_ids else None)

    # Lab turnaround: median collection -> result hours.
    turnarounds = []
    for lab in labs:
        hours = _hours_between(lab.get("collected_at", ""),
                               lab.get("result_at", ""))
        if hours is not None and hours >= 0:
            turnarounds.append(hours)
    turnaround_median = _median(turnarounds)

    # Medication reconciliation: encounters with >= 1 clean medication.
    med_encounters = {m["encounter_id"] for m in meds}
    reconciled = sum(1 for eid in encounter_ids if eid in med_encounters)
    med_reconciliation = (100.0 * reconciled / len(encounter_ids)
                          if encounter_ids else None)

    # Data-quality pass rate over every row loaded.
    quarantined_count = len(quarantined)
    pass_rate = (100.0 * (total_rows - quarantined_count) / total_rows
                 if total_rows else None)

    # Return-visit rate: patients with two encounters <= 30 days apart.
    by_patient = {}
    for e in encounters:
        by_patient.setdefault(e["patient_id"], []).append(e["encounter_date"])
    returning = 0
    for dates in by_patient.values():
        ordered = sorted(dates)
        for a, b in zip(ordered, ordered[1:]):
            d0 = datetime.strptime(a, "%Y-%m-%d")
            d1 = datetime.strptime(b, "%Y-%m-%d")
            if (d1 - d0).days <= 30:
                returning += 1
                break
    return_rate = (100.0 * returning / len(by_patient)
                   if by_patient else None)

    return {
        "encounters_total": len(encounters),
        "patients_total": len(by_patient),
        "vitals_total": len(vitals),
        "labs_total": len(labs),
        "medications_total": len(meds),
        "rows_total": total_rows,
        "rows_quarantined": quarantined_count,
        "vitals_completeness_pct": (round(vitals_completeness, 2)
                                    if vitals_completeness is not None else None),
        "lab_turnaround_median_hours": (round(turnaround_median, 2)
                                        if turnaround_median is not None else None),
        "med_reconciliation_pct": (round(med_reconciliation, 2)
                                   if med_reconciliation is not None else None),
        "data_quality_pass_rate_pct": (round(pass_rate, 2)
                                       if pass_rate is not None else None),
        "return_visit_rate_pct": (round(return_rate, 2)
                                  if return_rate is not None else None),
    }
