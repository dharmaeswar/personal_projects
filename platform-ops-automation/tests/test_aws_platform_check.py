"""Tests for ops.aws_platform_check — AWS platform configuration
checks (EKS, Kafka, RDS Aurora, Cloud Foundation, storage/backup).
All inputs are synthetic demo configs; no real AWS account is used."""

from ops.aws_platform_check import (
    check_cloud_foundation,
    check_eks_cluster,
    check_kafka_cluster,
    check_platform,
    check_rds_aurora,
    check_storage_backup,
    demo_config,
    platform_report,
)


def _statuses(checks):
    return {c["name"]: c["status"] for c in checks}


def _good_eks():
    return {
        "version": "1.30",
        "node_groups": [
            {"name": "general", "zones": ["us-east-1a", "us-east-1b"],
             "min_size": 2},
        ],
        "control_plane_logging": True,
        "secrets_encryption": True,
        "endpoint_public_access": False,
    }


def _good_kafka():
    return {
        "broker_count": 3,
        "default_replication_factor": 3,
        "min_insync_replicas": 2,
        "storage_encrypted": True,
        "tls_in_transit": "required",
        "version": "3.7.0",
    }


def _good_aurora():
    return {
        "engine": "aurora-postgresql",
        "backup_retention_days": 14,
        "instance_count": 2,
        "storage_encrypted": True,
        "deletion_protection": True,
    }


def _good_foundation():
    return {
        "stacks": [
            {"name": "network",
             "tags": {"owner": "platform", "environment": "prod",
                      "cost-center": "eng"},
             "ingress_rules": [{"name": "ssh", "cidr": "10.0.0.0/16"}]},
        ],
        "sso_enabled": True,
        "cloudtrail_enabled": True,
    }


def _good_storage():
    return {
        "backup_plan": "daily-platform",
        "retention_days": 35,
        "vault_encrypted": True,
        "hours_since_last_success": 5,
        "lifecycle_to_cold": True,
    }


def test_eks_good_config_passes_all():
    assert all(c["status"] == "pass" for c in check_eks_cluster(_good_eks()))


def test_eks_old_version_fails():
    cfg = _good_eks()
    cfg["version"] = "1.26"
    assert _statuses(check_eks_cluster(cfg))["eks-version-supported"] == "fail"


def test_eks_single_az_fails():
    cfg = _good_eks()
    cfg["node_groups"] = [{"name": "g", "zones": ["us-east-1a"], "min_size": 2}]
    assert _statuses(check_eks_cluster(cfg))["eks-multi-az-nodes"] == "fail"


def test_eks_logging_off_fails():
    cfg = _good_eks()
    cfg["control_plane_logging"] = False
    assert _statuses(check_eks_cluster(cfg))["eks-control-plane-logging"] == "fail"


def test_eks_open_endpoint_fails():
    cfg = _good_eks()
    cfg["endpoint_public_access"] = True
    assert _statuses(check_eks_cluster(cfg))["eks-endpoint-restricted"] == "fail"


def test_kafka_good_config_passes_all():
    assert all(c["status"] == "pass" for c in check_kafka_cluster(_good_kafka()))


def test_kafka_low_replication_fails():
    cfg = _good_kafka()
    cfg["default_replication_factor"] = 2
    assert _statuses(check_kafka_cluster(cfg))["kafka-replication-factor"] == "fail"


def test_kafka_unencrypted_storage_fails():
    cfg = _good_kafka()
    cfg["storage_encrypted"] = False
    assert _statuses(check_kafka_cluster(cfg))["kafka-storage-encrypted"] == "fail"


def test_aurora_good_config_passes_all():
    assert all(c["status"] == "pass" for c in check_rds_aurora(_good_aurora()))


def test_aurora_short_retention_fails():
    cfg = _good_aurora()
    cfg["backup_retention_days"] = 3
    assert _statuses(check_rds_aurora(cfg))["aurora-backup-retention"] == "fail"


def test_aurora_non_aurora_engine_fails():
    cfg = _good_aurora()
    cfg["engine"] = "postgres"
    assert _statuses(check_rds_aurora(cfg))["aurora-engine"] == "fail"


def test_foundation_good_config_passes_all():
    assert all(c["status"] == "pass"
               for c in check_cloud_foundation(_good_foundation()))


def test_foundation_missing_tag_fails():
    cfg = _good_foundation()
    cfg["stacks"][0]["tags"] = {"owner": "platform"}
    assert _statuses(check_cloud_foundation(cfg))["foundation-required-tags"] == "fail"


def test_foundation_public_ingress_fails():
    cfg = _good_foundation()
    cfg["stacks"][0]["ingress_rules"] = [{"name": "web", "cidr": "0.0.0.0/0"}]
    assert _statuses(check_cloud_foundation(cfg))["foundation-no-public-ingress"] == "fail"


def test_foundation_sso_off_fails():
    cfg = _good_foundation()
    cfg["sso_enabled"] = False
    assert _statuses(check_cloud_foundation(cfg))["foundation-sso-federation"] == "fail"


def test_storage_good_config_passes_all():
    assert all(c["status"] == "pass"
               for c in check_storage_backup(_good_storage()))


def test_storage_stale_backup_fails():
    cfg = _good_storage()
    cfg["hours_since_last_success"] = 30
    assert _statuses(check_storage_backup(cfg))["backup-recent-success"] == "fail"


def test_demo_config_has_three_failures():
    checks = check_platform(demo_config())
    report = platform_report(checks)
    assert report["overall"] == "fail"
    assert report["failed"] == 3
    assert report["failed_checks"] == [
        "eks-control-plane-logging",
        "kafka-replication-factor",
        "foundation-required-tags",
    ]


def test_platform_report_counts():
    checks = [{"name": "a", "status": "pass", "detail": ""},
              {"name": "b", "status": "fail", "detail": ""}]
    report = platform_report(checks)
    assert report == {"overall": "fail", "passed": 1, "failed": 1,
                      "failed_checks": ["b"]}
