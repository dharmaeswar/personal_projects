"""Tests for ops.multicloud_iac — multi-cloud IaC plan validation,
secret rotation audit, and transfer-cost estimation."""

from datetime import date

import pytest

from ops.multicloud_iac import (
    check_plan,
    check_secrets,
    demo_plan,
    demo_secrets,
    estimate_transfer_cost,
    iac_report,
)

TODAY = date(2026, 11, 20)


def _resource(cloud="aws", rtype="aws_eks_cluster", tags=None,
              public_ingress=False, secret_ref="vault"):
    return {
        "cloud": cloud,
        "type": rtype,
        "tags": {"env": "prod"} if tags is None else tags,
        "public_ingress": public_ingress,
        "secret_ref": secret_ref,
    }


def _by_name(checks, name):
    return next(c for c in checks if c["name"] == name)


def test_clean_plan_passes_all_checks():
    plan = {"resources": [_resource(), _resource(cloud="gcp",
            rtype="google_compute_instance")]}
    checks = check_plan(plan)
    assert all(c["status"] == "pass" for c in checks)
    assert len(checks) == 4


def test_untagged_resource_fails_tag_check():
    plan = {"resources": [_resource(tags={})]}
    assert _by_name(check_plan(plan), "all-resources-tagged")["status"] == "fail"


def test_open_ingress_fails_ingress_check():
    plan = {"resources": [_resource(public_ingress=True)]}
    assert _by_name(check_plan(plan), "no-open-ingress")["status"] == "fail"


def test_plaintext_secret_fails_vault_check():
    plan = {"resources": [_resource(secret_ref="plaintext")]}
    assert _by_name(check_plan(plan), "secrets-via-vault")["status"] == "fail"


def test_single_cloud_fails_redundancy_check():
    plan = {"resources": [_resource()]}
    check = _by_name(check_plan(plan), "multi-cloud-redundancy")
    assert check["status"] == "fail"
    assert "1 cloud" in check["detail"]


def test_two_clouds_pass_redundancy_check():
    plan = {"resources": [_resource(), _resource(cloud="azure",
            rtype="azurerm_kubernetes_cluster")]}
    assert _by_name(check_plan(plan), "multi-cloud-redundancy")["status"] == "pass"


def test_empty_plan_fails_tag_and_redundancy():
    checks = check_plan({"resources": []})
    assert _by_name(checks, "multi-cloud-redundancy")["status"] == "fail"


def test_fresh_secret_passes_rotation_check():
    checks = check_secrets([{"name": "db-password", "last_rotated": "2026-11-10"}], TODAY)
    assert checks[0]["status"] == "pass"


def test_stale_secret_fails_rotation_check():
    checks = check_secrets([{"name": "api-key", "last_rotated": "2026-07-22"}], TODAY)
    assert checks[0]["status"] == "fail"
    assert "121 days" in checks[0]["detail"]


def test_secret_at_limit_passes():
    checks = check_secrets([{"name": "token", "last_rotated": "2026-08-22"}], TODAY)
    assert checks[0]["status"] == "pass"


def test_transfer_cost_picks_cheapest_path():
    result = estimate_transfer_cost(
        500, {"aws-to-gcp": 0.09, "aws-to-azure": 0.08, "gcp-to-azure": 0.07}
    )
    assert result["costs"] == {
        "aws-to-gcp": 45.0, "aws-to-azure": 40.0, "gcp-to-azure": 35.0,
    }
    assert result["cheapest"] == "gcp-to-azure"


def test_transfer_cost_empty_rates_has_no_cheapest():
    result = estimate_transfer_cost(100, {})
    assert result["costs"] == {}
    assert result["cheapest"] is None


def test_iac_report_counts_failures():
    report = iac_report(check_plan(demo_plan()), check_secrets(demo_secrets(), TODAY))
    assert report["overall"] == "fail"
    assert report["failed"] == 3
    assert report["passed"] == 3
    assert "all-resources-tagged" in report["failed_checks"]


def test_iac_report_passes_when_clean():
    plan = {"resources": [_resource(), _resource(cloud="gcp",
            rtype="google_compute_instance")]}
    secrets = [{"name": "db-password", "last_rotated": "2026-11-10"}]
    report = iac_report(check_plan(plan), check_secrets(secrets, TODAY))
    assert report["overall"] == "pass"
    assert report["failed"] == 0
