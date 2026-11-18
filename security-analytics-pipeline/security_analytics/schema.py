"""Expected schemas for the staged and normalized security tables."""

from __future__ import annotations

# Staged raw tables keep source rows exactly as received (nothing cleaned).
STAGED_SCHEMAS = {
    "raw_login_events": {
        "event_id": ("TEXT", False),
        "identity_id": ("TEXT", True),
        "ts": ("TEXT", False),
        "ip": ("TEXT", True),
        "country": ("TEXT", True),
        "city": ("TEXT", True),
        "success": ("INTEGER", False),
        "mfa_used": ("INTEGER", False),
    },
    "raw_audit_events": {
        "event_id": ("TEXT", False),
        "identity_id": ("TEXT", False),
        "asset_id": ("TEXT", False),
        "action": ("TEXT", False),
        "ts": ("TEXT", False),
        "result": ("TEXT", False),
    },
    "raw_findings": {
        "finding_id": ("TEXT", False),
        "asset_id": ("TEXT", False),
        "severity": ("TEXT", False),
        "title": ("TEXT", False),
        "discovered_date": ("TEXT", False),
        "due_date": ("TEXT", False),
        "status": ("TEXT", False),
        "remediated_date": ("TEXT", True),
    },
}

# Normalized security data model: dimensions plus one unified events table.
NORMALIZED_SCHEMAS = {
    "identities": {
        "identity_id": ("TEXT", False),
        "name": ("TEXT", False),
        "email": ("TEXT", False),
        "department": ("TEXT", False),
        "privileged": ("INTEGER", False),
        "mfa_enabled": ("INTEGER", False),
        "last_login_days_ago": ("INTEGER", False),
        "status": ("TEXT", False),
    },
    "assets": {
        "asset_id": ("TEXT", False),
        "hostname": ("TEXT", False),
        "asset_type": ("TEXT", False),
        "owner_identity_id": ("TEXT", False),
        "criticality": ("TEXT", False),
        "last_seen_days_ago": ("INTEGER", False),
    },
    "events": {
        "event_id": ("TEXT", False),
        "event_type": ("TEXT", False),
        "identity_id": ("TEXT", True),
        "asset_id": ("TEXT", True),
        "ts": ("TEXT", False),
        "country": ("TEXT", True),
        "city": ("TEXT", True),
        "ip": ("TEXT", True),
        "success": ("INTEGER", True),
        "mfa_used": ("INTEGER", True),
        "action": ("TEXT", True),
        "result": ("TEXT", True),
        "late_arriving": ("INTEGER", False),
        "source_event_id": ("TEXT", False),
    },
    "findings": {
        "finding_id": ("TEXT", False),
        "asset_id": ("TEXT", False),
        "severity": ("TEXT", False),
        "title": ("TEXT", False),
        "discovered_date": ("TEXT", False),
        "due_date": ("TEXT", False),
        "status": ("TEXT", False),
        "remediated_date": ("TEXT", True),
    },
    "quarantine": {
        "source_table": ("TEXT", False),
        "source_id": ("TEXT", False),
        "reason": ("TEXT", False),
    },
}
