"""Middleware security: CVE patch plans, TLS/PKI hardening and
least-privilege access checks for the messaging platform.

Local simulation only: findings and configs are plain dicts supplied
by the caller (for example, parsed from a scanner report). Nothing
here scans a real host, touches a real broker, or applies a real
patch. The module answers the middleware-engineer question: is this
patch safe to roll out, and is this broker config hardened?
"""

from __future__ import annotations

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1,
                 "info": 0}

WEAK_CIPHERS = {"RC4", "DES", "3DES", "NULL", "EXPORT", "MD5"}

TLS_MINIMUM = "1.2"


def _rank(severity: str) -> int:
    try:
        return SEVERITY_RANK[severity.lower()]
    except KeyError:
        raise ValueError(f"unknown severity {severity!r}") from None


def triage_findings(findings: list[dict]) -> dict:
    """Sort open scanner findings by severity and count them.

    Each finding is a dict with ``cve``, ``severity``, ``component``
    and ``status`` (``open``, ``fixed`` or ``accepted-risk``).
    Returns counts per severity plus the open critical/high findings,
    most severe first, so patching can be prioritised.
    """
    by_severity: dict[str, int] = {}
    open_critical_high = []
    total_open = 0
    for finding in findings:
        severity = finding["severity"].lower()
        _rank(severity)  # raises on unknown severity
        if finding["status"] == "open":
            total_open += 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            if _rank(severity) >= _rank("high"):
                open_critical_high.append(finding)
    open_critical_high.sort(key=lambda f: -_rank(f["severity"]))
    return {"by_severity": by_severity,
            "open_critical_high": open_critical_high,
            "total_open": total_open}


def validate_patch_plan(plan: dict) -> list[str]:
    """Check a CVE patch plan is safe to roll out. Returns blockers.

    The plan is a dict with ``component``, ``current_version``,
    ``target_version``, ``cves`` (list of CVE ids the patch fixes),
    ``pre_patch_checks`` and ``post_patch_checks`` (named regression
    checks), ``nonprod_validated`` (was the patch proven in a
    non-production environment first) and ``rollback_plan`` (is there
    a way back). An empty list means the plan is ready to run.
    """
    blockers = []
    if not plan.get("cves"):
        blockers.append("no CVEs listed: patch has no stated fix")
    if plan.get("current_version") == plan.get("target_version"):
        blockers.append("target version equals current version: "
                        "nothing to patch")
    if not plan.get("pre_patch_checks"):
        blockers.append("no pre-patch checks: baseline is unmeasured")
    if not plan.get("post_patch_checks"):
        blockers.append("no post-patch checks: regression cannot be "
                        "proven after the patch")
    if not plan.get("nonprod_validated"):
        blockers.append("patch not validated in non-production first")
    if not plan.get("rollback_plan"):
        blockers.append("no rollback plan if the patch breaks the "
                        "broker")
    return blockers


def _tls_version_ok(version: str) -> bool:
    return tuple(int(p) for p in version.split(".")) >= (1, 2)


def check_tls_config(config: dict) -> list[dict]:
    """Review a broker TLS/PKI config against hardening rules.

    The config is a dict with ``tls_min_version``, ``cipher``,
    ``cert_expires_in_days``, ``mutual_tls`` and
    ``encryption_at_rest``. Returns findings, each a dict with
    ``severity``, ``rule`` and ``detail``.
    """
    findings = []
    if not _tls_version_ok(str(config.get("tls_min_version", ""))):
        findings.append({"severity": "critical", "rule": "tls_version",
                         "detail": "TLS minimum below 1.2; old clients "
                                   "can negotiate weak encryption"})
    cipher = str(config.get("cipher", "")).upper()
    if any(weak in cipher for weak in WEAK_CIPHERS):
        findings.append({"severity": "high", "rule": "weak_cipher",
                         "detail": f"cipher {config.get('cipher')} is on "
                                   "the weak list"})
    days = config.get("cert_expires_in_days")
    if days is not None and days < 30:
        findings.append({"severity": "high" if days < 14 else "medium",
                         "rule": "cert_expiry",
                         "detail": f"certificate expires in {days} day(s)"})
    if not config.get("mutual_tls"):
        findings.append({"severity": "medium", "rule": "mutual_tls",
                         "detail": "mutual TLS is off; clients are not "
                                   "authenticated by certificate"})
    if not config.get("encryption_at_rest"):
        findings.append({"severity": "high", "rule": "encryption_at_rest",
                         "detail": "encryption at rest is off for stored "
                                   "messages"})
    return findings


def check_acls(acls: list[dict], known_principals: set[str]) -> list[dict]:
    """Check broker ACLs for least-privilege violations.

    Each ACL is a dict with ``principal``, ``resource`` and
    ``permission`` (``read``, ``write`` or ``admin``). A wildcard
    resource with write/admin access, or an unknown principal, is a
    violation. Returns violations as dicts with ``severity``,
    ``rule`` and ``detail``.
    """
    violations = []
    for acl in acls:
        permission = acl["permission"].lower()
        if permission not in ("read", "write", "admin"):
            raise ValueError(f"unknown permission {acl['permission']!r}")
        if acl["resource"] == "*" and permission in ("write", "admin"):
            violations.append({"severity": "critical",
                               "rule": "wildcard_write",
                               "detail": f"{acl['principal']} has "
                                         f"{permission} on every resource"})
        if acl["principal"] not in known_principals:
            violations.append({"severity": "high",
                               "rule": "unknown_principal",
                               "detail": f"ACL for unknown principal "
                                         f"{acl['principal']}"})
    return violations


def patch_readiness_report(plan: dict, findings: list[dict],
                           tls_config: dict, acls: list[dict],
                           known_principals: set[str]) -> dict:
    """Combine plan, scan, TLS and ACL checks into one verdict.

    ``ready`` is True only when the patch plan has no blockers, no
    open critical/high findings remain, and neither the TLS config
    nor the ACLs carry a critical or high problem.
    """
    blockers = validate_patch_plan(plan)
    triaged = triage_findings(findings)
    tls = check_tls_config(tls_config)
    acl_violations = check_acls(acls, known_principals)
    severe_tls = [f for f in tls if _rank(f["severity"]) >= _rank("high")]
    severe_acls = [v for v in acl_violations
                   if _rank(v["severity"]) >= _rank("high")]
    ready = (not blockers and not triaged["open_critical_high"]
             and not severe_tls and not severe_acls)
    return {"blockers": blockers,
            "open_critical_high": triaged["open_critical_high"],
            "tls_findings": tls,
            "acl_violations": acl_violations,
            "ready": ready}
