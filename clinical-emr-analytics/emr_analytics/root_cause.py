"""Root-cause analysis over quarantined rows.

Groups the quarantine list by (feed, rule), ranks the groups by count,
and attaches a candidate cause and a suggested fix for each rule. The
cause is labelled a *candidate*: it is the most likely explanation
given the pattern, not a proven fact — the fix is what a data team
would check first with the source-system owner.
"""

RULE_CAUSES = {
    "UNKNOWN_ENCOUNTER": (
        "Child record references an encounter missing from the encounter "
        "feed — the encounter extract is incomplete, or the child feed "
        "covers a wider window than the encounter feed.",
        "Re-extract the encounter feed for the same window and confirm "
        "the child feed's date filter matches it.",
    ),
    "FUTURE_TIMESTAMP": (
        "Timestamp dated after the run date — source clock skew, a "
        "timezone applied twice, or a placeholder date in the source.",
        "Check the source system's clock/timezone handling and reject "
        "placeholder dates (e.g. 9999 or far-future defaults) at extract.",
    ),
    "OUT_OF_RANGE": (
        "Value outside the plausible clinical range — wrong unit sent by "
        "the source, a device calibration problem, or a free-text value "
        "parsed as a number.",
        "Confirm the unit the source sends for this concept and check "
        "device calibration; add a unit assertion to the extract.",
    ),
    "DUPLICATE": (
        "Same observation sent twice — the feed was re-sent without an "
        "idempotency key, or the extract ran twice over the same window.",
        "Add an idempotency key (encounter + concept + timestamp) to the "
        "extract and de-duplicate on load.",
    ),
    "RESULT_BEFORE_COLLECTION": (
        "Result timestamped before collection — collection/result clocks "
        "disagree, or the two timestamps were swapped in the feed.",
        "Verify the source's timestamp mapping and add a "
        "result >= collection assertion to the extract.",
    ),
    "INVALID_DOSE": (
        "Dose is zero/negative or uses a unit the vocabulary does not "
        "know — an e-prescribing mapping gap or a defaulted dose field.",
        "Map the source's dose units into the standard vocabulary and "
        "reject zero doses at order entry.",
    ),
}


def analyze(quarantined):
    """Return findings sorted by count descending.

    Each finding: {"feed", "rule", "count", "share_pct",
    "candidate_cause", "suggested_fix", "example_ids": [...]}.
    """
    groups = {}
    for item in quarantined:
        for rule in item["rules"]:
            key = (item["feed"], rule)
            groups.setdefault(key, []).append(item["row"])
    total = len(quarantined) or 1
    findings = []
    for (feed, rule), rows in groups.items():
        cause, fix = RULE_CAUSES.get(rule, ("Unknown pattern.", "Investigate."))
        id_field = {"vitals": "vital_id", "labs": "lab_id",
                    "medications": "med_id", "encounters": "encounter_id"}.get(feed, "")
        findings.append({
            "feed": feed,
            "rule": rule,
            "count": len(rows),
            "share_pct": round(100.0 * len(rows) / total, 1),
            "candidate_cause": cause,
            "suggested_fix": fix,
            "example_ids": [r.get(id_field) for r in rows[:3]],
        })
    findings.sort(key=lambda f: (-f["count"], f["feed"], f["rule"]))
    return findings
