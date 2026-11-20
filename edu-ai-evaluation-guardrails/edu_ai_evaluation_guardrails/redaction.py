"""Privacy-aware handling of institutional data.

Redacts personally identifying information from tutor prompts and
responses BEFORE they reach any grader or log. Redaction is
deterministic and auditable: every replacement is recorded as a
(count, kind) pair so a run log can prove what was removed without
keeping the original value.
"""

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}\b")
STUDENT_ID_RE = re.compile(r"\b(?:SID|Student\s?ID|ID)[-:\s]?\d{6,10}\b", re.IGNORECASE)
# US-style student number on its own: 8-10 digits, not part of a longer number.
BARE_ID_RE = re.compile(r"(?<![\d.])\d{8,10}(?![\d.])")

# Common PII-adjacent tokens that must never be logged raw.
TOKEN_MAP = {
    EMAIL_RE: "[EMAIL]",
    PHONE_RE: "[PHONE]",
    STUDENT_ID_RE: "[STUDENT-ID]",
}


def redact_text(text, known_names=()):
    """Redact PII from text.

    Args:
        text: raw tutor prompt or response.
        known_names: iterable of student/staff full names to redact.

    Returns:
        (redacted_text, redactions) where redactions is a dict of
        placeholder -> count of replacements made.
    """
    redactions = {}
    out = text
    for pattern, placeholder in TOKEN_MAP.items():
        matches = pattern.findall(out)
        if matches:
            redactions[placeholder] = redactions.get(placeholder, 0) + len(matches)
            out = pattern.sub(placeholder, out)
    for name in known_names:
        if name and name in out:
            count = out.count(name)
            redactions["[NAME]"] = redactions.get("[NAME]", 0) + count
            out = out.replace(name, "[NAME]")
    # Bare 8-10 digit numbers (likely student IDs) only after labelled
    # patterns are handled, so dates and years are left alone.
    bare = BARE_ID_RE.findall(out)
    bare = [b for b in bare if not (1900 <= int(b[:4]) <= 2100 and len(b) == 8)]
    if bare:
        redactions["[STUDENT-ID]"] = redactions.get("[STUDENT-ID]", 0) + len(bare)
        for b in bare:
            out = out.replace(b, "[STUDENT-ID]", 1)
    return out, redactions


def contains_pii(text):
    """Quick check: True if any PII pattern is still present in text."""
    if EMAIL_RE.search(text) or PHONE_RE.search(text):
        return True
    if STUDENT_ID_RE.search(text):
        return True
    return False
