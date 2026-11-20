"""Feature extraction from synthetic inbound email messages.

Every feature is computed from fields present on a message dict; nothing
here calls a network service or an LLM. All messages processed by this
project are synthetic and generated locally (see detection/pipeline.py).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Domains that commonly host free personal mail. A business-context message
# arriving from one is a (weak) spoof signal, not proof of attack.
FREE_MAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "protonmail.com", "icloud.com", "aol.com",
}

# Attachment extensions commonly abused in phishing / malware delivery.
RISKY_EXTENSIONS = {
    ".exe", ".scr", ".bat", ".cmd", ".vbs", ".js", ".jar",
    ".zip", ".rar", ".iso", ".lnk", ".ps1", ".msi",
}

# TLDs that appear disproportionately in phishing URLs in public
# threat reports. Used only as a weak signal inside a weighted score.
SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".buzz", ".work", ".live",
    ".online", ".site", ".fun", ".icu", ".shop", ".tk", ".ml", ".ga",
}

URGENCY_KEYWORDS = {
    "urgent", "immediately", "asap", "wire transfer", "gift card",
    "verify your account", "password expires", "account suspended",
    "action required", "confidential", "do not share", "payment overdue",
    "invoice attached", "reset your password", "click here",
}

# Display names of senior staff used to test display-name spoofing.
# In production this would come from the company directory; here it is a
# fixed synthetic list.
KNOWN_EXEC_NAMES = {"sarah chen", "michael ortiz", "priya nair", "david kim"}

URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def _domain_of(email: str) -> str:
    """Return the lower-cased domain part of an email address, or ''."""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].strip().lower()


def _levenshtein(a: str, b: str) -> int:
    """Small edit-distance helper for lookalike-domain detection."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def extract_urls(text: str) -> list[str]:
    """All http(s) URLs found in a text body."""
    return URL_RE.findall(text or "")


def is_lookalike_domain(domain: str, trusted: str) -> bool:
    """True when a domain is a near-miss of a trusted domain (typosquat)."""
    domain = domain.lower().strip()
    trusted = trusted.lower().strip()
    if not domain or domain == trusted:
        return False
    # Same registrable shape, one or two edits away, e.g. acme-corp.com
    # vs acmecorp.com, or acmec0rp.com.
    return _levenshtein(domain, trusted) <= 2


def extract_features(message: dict, trusted_domain: str = "acmecorp.com") -> dict:
    """Extract a flat feature dict from one synthetic message.

    Expected message keys (all optional except ``sender``):
    sender, display_name, reply_to, subject, body, urls (list),
    attachments (list of filenames), spf_pass, dkim_pass, dmarc_pass,
    known_sender (bool: sender seen before in this tenant).
    """
    sender = (message.get("sender") or "").strip().lower()
    display_name = (message.get("display_name") or "").strip()
    reply_to = (message.get("reply_to") or "").strip().lower()
    subject = message.get("subject") or ""
    body = message.get("body") or ""
    urls = list(message.get("urls") or extract_urls(body))
    attachments = list(message.get("attachments") or [])

    sender_domain = _domain_of(sender)
    reply_domain = _domain_of(reply_to)

    text = f"{subject}\n{body}".lower()
    url_hosts = []
    suspicious_tld_count = 0
    ip_host_count = 0
    for url in urls:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            host = ""
        url_hosts.append(host)
        if any(host.endswith(tld) for tld in SUSPICIOUS_TLDS):
            suspicious_tld_count += 1
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host or ""):
            ip_host_count += 1

    risky_attachments = [
        a for a in attachments
        if any(a.lower().endswith(ext) for ext in RISKY_EXTENSIONS)
    ]
    urgency_hits = sorted({kw for kw in URGENCY_KEYWORDS if kw in text})
    auth_failures = sum(
        1 for k in ("spf_pass", "dkim_pass", "dmarc_pass")
        if message.get(k) is False
    )

    display_name_spoof = (
        display_name.lower() in KNOWN_EXEC_NAMES
        and sender_domain != trusted_domain
    )

    features = {
        # Identity / sender signals
        "sender_domain_mismatch": bool(
            sender_domain and sender_domain != trusted_domain
        ),
        "display_name_spoof": bool(display_name_spoof),
        "reply_to_mismatch": bool(reply_domain and reply_domain != sender_domain),
        "free_sender_domain": sender_domain in FREE_MAIL_DOMAINS,
        "lookalike_domain": is_lookalike_domain(sender_domain, trusted_domain),
        "unknown_sender": not bool(message.get("known_sender", False)),
        # Authentication signals
        "auth_failures": auth_failures,
        "spf_fail": message.get("spf_pass") is False,
        "dkim_fail": message.get("dkim_pass") is False,
        "dmarc_fail": message.get("dmarc_pass") is False,
        # URL signals
        "url_count": len(urls),
        "suspicious_tld_count": suspicious_tld_count,
        "ip_host_url_count": ip_host_count,
        "has_url": len(urls) > 0,
        # Attachment signals
        "attachment_count": len(attachments),
        "risky_attachment_count": len(risky_attachments),
        "has_risky_attachment": len(risky_attachments) > 0,
        # Content signals
        "urgency_keyword_count": len(urgency_hits),
        "urgency_keywords": urgency_hits,
        "subject_all_caps": bool(subject) and subject == subject.upper() and any(c.isalpha() for c in subject),
        "body_length_chars": len(body),
    }
    return features


def feature_vector(features: dict) -> dict[str, float]:
    """Numeric view of the feature dict, for the scorer."""
    return {
        "sender_domain_mismatch": float(features["sender_domain_mismatch"]),
        "display_name_spoof": float(features["display_name_spoof"]),
        "reply_to_mismatch": float(features["reply_to_mismatch"]),
        "free_sender_domain": float(features["free_sender_domain"]),
        "lookalike_domain": float(features["lookalike_domain"]),
        "unknown_sender": float(features["unknown_sender"]),
        "auth_failures": float(features["auth_failures"]),
        "url_count": float(min(features["url_count"], 5)),
        "suspicious_tld_count": float(features["suspicious_tld_count"]),
        "ip_host_url_count": float(features["ip_host_url_count"]),
        "risky_attachment_count": float(features["risky_attachment_count"]),
        "urgency_keyword_count": float(min(features["urgency_keyword_count"], 5)),
        "subject_all_caps": float(features["subject_all_caps"]),
    }
