"""PHI redaction for logs, audit trails and outbound text.

Patterns covered: patient names from the roster, medical record numbers,
dates of birth, phone numbers, email addresses and SSN-shaped strings.
Redaction runs before anything is written to the audit log, so no PHI ever
lands in a log line. This is a demo safeguard, not a HIPAA certification.
"""

import re

from .kb import PATIENTS

_PATTERNS = [
    ("MRN", re.compile(r"MRN[-\s]?\d{6,}", re.IGNORECASE)),
    ("DOB", re.compile(r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/(19|20)\d{2}\b")),
    ("PHONE", re.compile(r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
]

_NAMES = sorted(
    (patient["name"] for patient in PATIENTS.values()),
    key=len,
    reverse=True,
)


def redact(text):
    """Return (redacted_text, findings) where findings list PHI types found."""
    findings = []
    redacted = str(text)
    for name in _NAMES:
        if name in redacted:
            redacted = redacted.replace(name, "[PATIENT NAME]")
            findings.append("NAME")
    for label, pattern in _PATTERNS:
        if pattern.search(redacted):
            redacted = pattern.sub(f"[{label}]", redacted)
            findings.append(label)
    return redacted, sorted(set(findings))


def contains_phi(text):
    """True when any PHI pattern (or a roster name) appears in the text."""
    _, findings = redact(text)
    return bool(findings)
