"""Monthly HEDIS quality-measure computation from the silver layer.

Four measures, for the measurement month (e.g. 2026-10), computed from
silver members, labs and screenings with the standard HEDIS-style
eligibility rules. The rules here are the simplified, documented form
used for the demo — real HEDIS specs add continuous-enrollment and
exclusion logic that is out of scope and is not claimed.

- BCS (Breast Cancer Screening): women 40-74 with a mammogram in the
  27 months before the end of the measurement month.
- COL (Colorectal Cancer Screening): members 45-75 with a colonoscopy in
  the last 10 years or a FIT test in the measurement year.
- CDC (HbA1c Control): members 18-75 with diabetes and an HbA1c result
  below 8.0 in the measurement year.
- CBP (Blood Pressure Control): members 18-85 with hypertension whose
  latest blood-pressure reading in the measurement year is below 140/90.
"""

from datetime import date

MEASURES = ["BCS", "COL", "CDC", "CBP"]


def _months_between(start, end):
    return (end.year - start.year) * 12 + (end.month - start.month)


def _parse(d):
    y, m, day = (int(p) for p in d.split("-"))
    return date(y, m, day)


def compute_hedis(conn, month):
    """Compute all four measures for ``month`` (YYYY-MM) and store gold.

    Idempotent: gold rows for the month are replaced, not duplicated.
    Returns a list of dicts {measure, denominator, numerator, rate}.
    """
    year, mon = (int(p) for p in month.split("-"))
    month_end = date(year, mon, 28)  # months used are Sep/Oct; day 28 safe
    members = conn.execute(
        "SELECT member_id, sex, age, diabetes, hypertension"
        " FROM silver_members").fetchall()
    labs = conn.execute(
        "SELECT member_id, test, result, result_date FROM silver_labs"
    ).fetchall()
    screenings = conn.execute(
        "SELECT member_id, screening_type, screening_date"
        " FROM silver_screenings").fetchall()

    labs_by_member = {}
    for member_id, test, result, result_date in labs:
        labs_by_member.setdefault(member_id, []).append(
            (test, result, result_date))
    screens_by_member = {}
    for member_id, kind, when in screenings:
        screens_by_member.setdefault(member_id, []).append((kind, when))

    results = []
    for measure in MEASURES:
        denom = numer = 0
        for member_id, sex, age, diabetes, hypertension in members:
            eligible, met = _evaluate(
                measure, member_id, sex, age, diabetes, hypertension,
                labs_by_member.get(member_id, []),
                screens_by_member.get(member_id, []),
                year, month_end)
            if eligible:
                denom += 1
                if met:
                    numer += 1
        rate = round(numer / denom, 4) if denom else 0.0
        results.append({"measure": measure, "measurement_month": month,
                        "denominator": denom, "numerator": numer,
                        "rate": rate})
    conn.execute("DELETE FROM gold_hedis_monthly WHERE measurement_month=?",
                 (month,))
    conn.executemany(
        "INSERT INTO gold_hedis_monthly"
        " (measure, measurement_month, denominator, numerator, rate)"
        " VALUES (?, ?, ?, ?, ?)",
        [(r["measure"], month, r["denominator"], r["numerator"], r["rate"])
         for r in results])
    conn.commit()
    return results


def _evaluate(measure, member_id, sex, age, diabetes, hypertension,
              labs, screenings, year, month_end):
    """Return (eligible, numerator_met) for one member and one measure."""
    if measure == "BCS":
        if not (sex == "F" and 40 <= age <= 74):
            return False, False
        for kind, when in screenings:
            if kind == "mammogram" and _months_between(
                    _parse(when), month_end) <= 27:
                return True, True
        return True, False
    if measure == "COL":
        if not 45 <= age <= 75:
            return False, False
        for kind, when in screenings:
            d = _parse(when)
            if kind == "colonoscopy" and (month_end - d).days <= 365 * 10:
                return True, True
            if kind == "FIT" and d.year == year:
                return True, True
        return True, False
    if measure == "CDC":
        if not (diabetes == "Y" and 18 <= age <= 75):
            return False, False
        for test, result, when in labs:
            if test == "HbA1c" and _parse(when).year == year:
                return True, float(result) < 8.0
        return True, False
    if measure == "CBP":
        if not (hypertension == "Y" and 18 <= age <= 85):
            return False, False
        readings = [(when, result) for test, result, when in labs
                    if test == "BP" and _parse(when).year == year]
        if not readings:
            return True, False
        readings.sort()
        systolic, diastolic = (int(p) for p in
                               readings[-1][1].split("/"))
        return True, systolic < 140 and diastolic < 90
    raise ValueError("unknown measure %s" % measure)
