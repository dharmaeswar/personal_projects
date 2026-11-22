"""Tests for retention enforcement and subject erasure."""

from governance.catalog import Catalog, Column, Dataset
from governance.erasure import process_erasure
from governance.retention import evaluate_dataset


def _dataset(name="members", retention_days=365, legal_hold=False, rows=None):
    return Dataset(
        name=name, owner_team="test", system="Snowflake",
        retention_days=retention_days, legal_hold=legal_hold,
        columns=[Column("subject_id", "string"), Column("email", "string")],
        rows=rows if rows is not None else [],
    )


def test_retain_within_window():
    action = evaluate_dataset(_dataset(retention_days=365), age_days=100)
    assert action.action == "retain"


def test_delete_candidate_past_retention():
    action = evaluate_dataset(_dataset(retention_days=365), age_days=400)
    assert action.action == "delete-candidate"


def test_age_exactly_at_retention_is_retained():
    action = evaluate_dataset(_dataset(retention_days=365), age_days=365)
    assert action.action == "retain"


def test_legal_hold_blocks_deletion_even_when_expired():
    action = evaluate_dataset(_dataset(retention_days=365, legal_hold=True), age_days=900)
    assert action.action == "held"
    assert action.legal_hold is True


def test_legal_hold_blocks_deletion_when_within_window_too():
    action = evaluate_dataset(_dataset(retention_days=365, legal_hold=True), age_days=10)
    assert action.action == "held"


def _erasure_catalog() -> Catalog:
    catalog = Catalog()
    catalog.register(_dataset("members", rows=[
        {"subject_id": "SUBJ-1", "email": "a@example.com"},
        {"subject_id": "SUBJ-2", "email": "b@example.com"},
        {"subject_id": "SUBJ-1", "email": "a2@example.com"},
    ]))
    catalog.register(_dataset("loan_applications", legal_hold=True, rows=[
        {"subject_id": "SUBJ-1", "email": "a@example.com"},
        {"subject_id": "SUBJ-3", "email": "c@example.com"},
    ]))
    catalog.register(_dataset("support_tickets", rows=[
        {"subject_id": "SUBJ-2", "email": "b@example.com"},
    ]))
    return catalog


def test_erasure_deletes_subject_everywhere_except_held():
    catalog = _erasure_catalog()
    report = process_erasure(catalog, "SUBJ-1")
    assert report.erased_total == 2
    members = catalog.get("members")
    assert all(row["subject_id"] != "SUBJ-1" for row in members.rows)
    assert len(members.rows) == 1  # only SUBJ-2 remains
    # Held dataset is untouched.
    held = catalog.get("loan_applications")
    assert any(row["subject_id"] == "SUBJ-1" for row in held.rows)
    assert report.held_datasets == ["loan_applications"]


def test_erasure_reports_not_found_datasets():
    catalog = _erasure_catalog()
    report = process_erasure(catalog, "SUBJ-1")
    entry = next(e for e in report.entries if e.dataset == "support_tickets")
    assert entry.outcome == "not-found"
    assert entry.records_removed == 0


def test_erasure_for_unknown_subject_erases_nothing():
    catalog = _erasure_catalog()
    report = process_erasure(catalog, "SUBJ-999")
    assert report.erased_total == 0
    assert report.held_datasets == []
    assert all(e.outcome == "not-found" for e in report.entries)


def test_erasure_does_not_touch_other_subjects():
    catalog = _erasure_catalog()
    process_erasure(catalog, "SUBJ-1")
    assert any(row["subject_id"] == "SUBJ-2" for row in catalog.get("members").rows)
    assert any(row["subject_id"] == "SUBJ-3" for row in catalog.get("loan_applications").rows)
