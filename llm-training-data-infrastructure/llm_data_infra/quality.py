"""Quality gates for ingested records.

Each gate returns (passed: bool, reason: str). Gates are deliberately
simple and deterministic: completeness, text-length bounds, allowed
modality, and a PII-pattern scan (email / SSN-like strings) that sends a
record to quarantine instead of dropping it silently.
"""
import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

MIN_TEXT_LEN = 10
MAX_TEXT_LEN = 100_000
ALLOWED_MODALITIES = {"text", "image", "audio", "multimodal"}


def check_completeness(payload: dict) -> tuple[bool, str]:
    if not isinstance(payload, dict) or not payload:
        return False, "empty payload"
    if "text" not in payload and "uri" not in payload:
        return False, "missing text and uri"
    return True, ""


def check_text_length(payload: dict) -> tuple[bool, str]:
    text = payload.get("text", "")
    if not isinstance(text, str):
        return False, "text is not a string"
    if len(text) < MIN_TEXT_LEN:
        return False, f"text too short ({len(text)} chars < {MIN_TEXT_LEN})"
    if len(text) > MAX_TEXT_LEN:
        return False, f"text too long ({len(text)} chars > {MAX_TEXT_LEN})"
    return True, ""


def check_modality(payload: dict, modality: str) -> tuple[bool, str]:
    if modality not in ALLOWED_MODALITIES:
        return False, f"unknown modality '{modality}'"
    return True, ""


def check_pii(payload: dict) -> tuple[bool, str]:
    text = payload.get("text", "")
    if EMAIL_RE.search(text):
        return False, "possible email address in text"
    if SSN_RE.search(text):
        return False, "possible SSN pattern in text"
    return True, ""


GATES = [check_completeness, check_text_length, check_pii]


def run_gates(payload: dict, modality: str) -> list[str]:
    """Return the list of failure reasons (empty = all gates passed)."""
    failures = []
    ok, reason = check_modality(payload, modality)
    if not ok:
        failures.append(reason)
    for gate in GATES:
        ok, reason = gate(payload)
        if not ok:
            failures.append(reason)
    return failures
