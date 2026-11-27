import pytest

from credit_review_bi.governance import (
    Catalog, CatalogEntry, AccessGovernor, default_catalog)


def test_default_catalog_covers_all_tables():
    catalog = default_catalog()
    assert catalog.datasets() == ["borrower_pii", "findings", "loans", "reviews"]
    assert catalog.get("loans").owner == "Credit Review"
    assert catalog.get("borrower_pii").sensitivity == "Restricted"


def test_restricted_datasets_listed():
    assert default_catalog().restricted_datasets() == ["borrower_pii"]


def test_analyst_can_read_internal_not_restricted():
    gov = AccessGovernor(default_catalog())
    assert gov.can_read("analyst", "loans") is True
    assert gov.can_read("analyst", "findings") is True
    assert gov.can_read("analyst", "borrower_pii") is False


def test_auditor_needs_audit_purpose_for_restricted():
    gov = AccessGovernor(default_catalog())
    assert gov.can_read("auditor", "borrower_pii", purpose="audit") is True
    assert gov.can_read("auditor", "borrower_pii", purpose="curiosity") is False


def test_admin_has_full_access_and_unknown_role_has_none():
    gov = AccessGovernor(default_catalog())
    assert gov.can_read("admin", "borrower_pii") is True
    assert gov.can_read("superuser", "loans") is False
    assert gov.can_read("analyst", "not_a_dataset") is False


def test_access_decisions_are_logged():
    gov = AccessGovernor(default_catalog())
    gov.can_read("analyst", "loans")
    gov.can_read("analyst", "borrower_pii")
    log = gov.access_log()
    assert len(log) == 2
    assert log[0]["allowed"] is True
    assert log[1]["allowed"] is False


def test_bad_sensitivity_rejected_at_registration():
    catalog = Catalog()
    with pytest.raises(ValueError):
        catalog.register(CatalogEntry("x", "Team", "System", "Top Secret", 30))
