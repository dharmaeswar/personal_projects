"""Tests for PHI governance: hashing, role checks, audit log."""

from homehealth import governance, warehouse


def test_hash_is_stable_and_not_plain_text():
    hashed = governance.hash_patient_name("P001", "Patient P001")
    assert hashed.startswith("sha256:")
    assert "Patient P001" not in hashed
    assert hashed == governance.hash_patient_name("P001", "Patient P001")


def test_hash_differs_across_patients():
    assert governance.hash_patient_name(
        "P001", "Patient P001"
    ) != governance.hash_patient_name("P002", "Patient P002")


def test_care_team_reads_plain_analyst_reads_hash():
    plain = governance.reporting_patient_name(
        "care_team", "P001", "Patient P001"
    )
    assert plain == "Patient P001"
    for role in ("analyst", "auditor", "unknown-role"):
        assert governance.reporting_patient_name(
            role, "P001", "Patient P001"
        ).startswith("sha256:")


def test_role_check():
    assert governance.can_read_identifiable("care_team") is True
    assert governance.can_read_identifiable("analyst") is False
    assert governance.can_read_identifiable("auditor") is False


def test_audit_log_records_load():
    conn = warehouse.connect()
    governance.audit(conn, "run-1", "load", "loaded 12, quarantined 4",
                     "2026-11-26")
    rows = conn.execute("SELECT * FROM audit_log").fetchall()
    assert len(rows) == 1
    assert rows[0]["run_id"] == "run-1"
    assert rows[0]["action"] == "load"
    assert "loaded 12" in rows[0]["detail"]
