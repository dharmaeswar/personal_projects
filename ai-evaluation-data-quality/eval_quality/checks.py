"""Data-quality checks for AI evaluation datasets (trust & safety).

Each check takes a list of records and returns a list of findings.
A record is a dict with keys: id, prompt, response, label, split, source.
A finding is a dict with keys: check, severity, record_id, detail.
"""

import re
from collections import Counter, defaultdict

ALLOWED_LABELS = {
    "violence",
    "self-harm",
    "hate",
    "sexual-content",
    "illicit-behavior",
    "safe",
}

# Phrases that must never appear in a record labelled "safe".
DISALLOWED_PHRASES = (
    "instructions to build an explosive device",
    "how to make a bomb",
    "how to forge a passport",
)

PII_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit-card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
}


def _finding(check, severity, record_id, detail):
    return {
        "check": check,
        "severity": severity,
        "record_id": record_id,
        "detail": detail,
    }


def check_completeness(records):
    """Every record needs an id, a non-empty prompt and a non-empty response."""
    findings = []
    seen_ids = set()
    for rec in records:
        rid = rec.get("id")
        if not rid:
            findings.append(
                _finding("completeness", "critical", None,
                         "record is missing an id")
            )
            continue
        if rid in seen_ids:
            findings.append(
                _finding("completeness", "critical", rid,
                         "duplicate record id")
            )
        seen_ids.add(rid)
        if not (rec.get("prompt") or "").strip():
            findings.append(
                _finding("completeness", "critical", rid,
                         "prompt is empty")
            )
        if not (rec.get("response") or "").strip():
            findings.append(
                _finding("completeness", "critical", rid,
                         "response is empty")
            )
    return findings


def check_labels(records, allowed_labels=None, disallowed_phrases=None):
    """Labels must come from the taxonomy; 'safe' records must not carry
    disallowed content."""
    allowed = set(allowed_labels) if allowed_labels else ALLOWED_LABELS
    banned = disallowed_phrases if disallowed_phrases is not None \
        else DISALLOWED_PHRASES
    findings = []
    for rec in records:
        label = rec.get("label")
        if label not in allowed:
            findings.append(
                _finding("label-consistency", "critical", rec.get("id"),
                         "label %r is not in the allowed taxonomy" % (label,))
            )
            continue
        if label == "safe":
            text = ((rec.get("prompt") or "") + " "
                    + (rec.get("response") or "")).lower()
            for phrase in banned:
                if phrase in text:
                    findings.append(
                        _finding("label-consistency", "critical",
                                 rec.get("id"),
                                 "labelled safe but text contains %r"
                                 % (phrase,))
                    )
    return findings


def check_coverage(records, min_per_category=3, split="eval"):
    """Every harm category needs at least min_per_category records in the
    given split, so no category goes unevaluated."""
    counts = Counter(
        rec.get("label") for rec in records if rec.get("split") == split
    )
    findings = []
    for label in sorted(ALLOWED_LABELS):
        if counts.get(label, 0) < min_per_category:
            findings.append(
                _finding("coverage", "warning", None,
                         "category %r has %d %s records, minimum is %d"
                         % (label, counts.get(label, 0), split,
                            min_per_category))
            )
    return findings, dict(counts)


def _normalise(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def check_leakage(records):
    """The same prompt must not appear in both train and eval splits, and
    must not be duplicated inside one split."""
    findings = []
    by_prompt = defaultdict(set)
    by_prompt_ids = defaultdict(list)
    for rec in records:
        key = _normalise(rec.get("prompt"))
        if not key:
            continue
        by_prompt[key].add(rec.get("split"))
        by_prompt_ids[key].append(rec.get("id"))
    for prompt, splits in by_prompt.items():
        ids = by_prompt_ids[prompt]
        if len(splits) > 1:
            findings.append(
                _finding("leakage", "critical", ids[0],
                         "prompt in both train and eval splits "
                         "(records %s)" % (", ".join(ids),))
            )
        elif len(ids) > 1:
            findings.append(
                _finding("leakage", "warning", ids[0],
                         "duplicate prompt inside one split "
                         "(records %s)" % (", ".join(ids),))
            )
    return findings


def check_pii(records):
    """Scan prompts and responses for PII patterns (email, phone, SSN,
    credit-card-like numbers)."""
    findings = []
    for rec in records:
        for field in ("prompt", "response"):
            text = rec.get(field) or ""
            for name, pattern in PII_PATTERNS.items():
                if pattern.search(text):
                    findings.append(
                        _finding("pii-scan", "critical", rec.get("id"),
                                 "%s pattern found in %s" % (name, field))
                    )
    return findings


def run_all_checks(records, min_per_category=3):
    """Run every check and return a report dict with a pass/fail gate."""
    coverage_findings, counts = check_coverage(records, min_per_category)
    findings = (
        check_completeness(records)
        + check_labels(records)
        + coverage_findings
        + check_leakage(records)
        + check_pii(records)
    )
    critical = sum(1 for f in findings if f["severity"] == "critical")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    by_check = Counter(f["check"] for f in findings)
    return {
        "summary": {
            "total_records": len(records),
            "total_findings": len(findings),
            "critical": critical,
            "warnings": warnings,
            "findings_by_check": dict(by_check),
            "gate": "FAIL" if critical else "PASS",
        },
        "coverage": counts,
        "findings": findings,
    }
