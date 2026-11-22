"""AWS platform configuration checks for the Platform Ops Automation
demo project.

Validates a synthetic AWS platform config (plain dicts) against the
checks an AWS DevOps engineer runs on a Cloud Foundation stack: EKS
cluster settings, Kafka (MSK) cluster settings, RDS Aurora settings,
Cloud Foundation guardrails (tags, ingress, SSO/federation) and
storage/backup settings. All inputs are demo data — no real AWS
account, cluster, or resource is contacted, and no production AWS
experience is claimed.
"""

MIN_EKS_VERSION = (1, 28)
MIN_BACKUP_RETENTION_DAYS = 7
MIN_STORAGE_BACKUP_RETENTION_DAYS = 30
REQUIRED_TAGS = ("owner", "environment", "cost-center")


def _check(name, ok, detail):
    return {"name": name, "status": "pass" if ok else "fail", "detail": detail}


def _version_tuple(version):
    parts = str(version).split(".")
    return tuple(int(p) for p in parts[:2])


def check_eks_cluster(cfg):
    """Validate an EKS cluster config dict."""
    checks = []
    version = _version_tuple(cfg.get("version", "0.0"))
    checks.append(_check(
        "eks-version-supported",
        version >= MIN_EKS_VERSION,
        f"EKS version {cfg.get('version')} "
        f"(minimum {'.'.join(str(p) for p in MIN_EKS_VERSION)})",
    ))
    node_groups = cfg.get("node_groups", [])
    zones = {zone for group in node_groups for zone in group.get("zones", [])}
    checks.append(_check(
        "eks-multi-az-nodes",
        len(zones) >= 2,
        f"node groups span {len(zones)} availability zone(s) (minimum 2)",
    ))
    min_size = min((g.get("min_size", 0) for g in node_groups), default=0)
    checks.append(_check(
        "eks-node-group-size",
        bool(node_groups) and min_size >= 2,
        f"smallest node group min size is {min_size} (minimum 2)",
    ))
    checks.append(_check(
        "eks-control-plane-logging",
        bool(cfg.get("control_plane_logging")),
        "control plane logging enabled"
        if cfg.get("control_plane_logging")
        else "control plane logging is off",
    ))
    checks.append(_check(
        "eks-secrets-encrypted",
        bool(cfg.get("secrets_encryption")),
        "Kubernetes secrets encrypted with KMS"
        if cfg.get("secrets_encryption")
        else "Kubernetes secrets are not KMS-encrypted",
    ))
    public = cfg.get("endpoint_public_access", True)
    checks.append(_check(
        "eks-endpoint-restricted",
        not public or bool(cfg.get("endpoint_public_cidrs")),
        "cluster endpoint is private or restricted to listed CIDRs"
        if not public or cfg.get("endpoint_public_cidrs")
        else "cluster endpoint is open to the public internet",
    ))
    return checks


def check_kafka_cluster(cfg):
    """Validate a Kafka (MSK) cluster config dict."""
    checks = []
    checks.append(_check(
        "kafka-broker-count",
        cfg.get("broker_count", 0) >= 3,
        f"{cfg.get('broker_count', 0)} broker(s) (minimum 3)",
    ))
    checks.append(_check(
        "kafka-replication-factor",
        cfg.get("default_replication_factor", 0) >= 3,
        f"default replication factor "
        f"{cfg.get('default_replication_factor', 0)} (minimum 3)",
    ))
    checks.append(_check(
        "kafka-min-insync-replicas",
        cfg.get("min_insync_replicas", 0) >= 2,
        f"min.insync.replicas "
        f"{cfg.get('min_insync_replicas', 0)} (minimum 2)",
    ))
    checks.append(_check(
        "kafka-storage-encrypted",
        bool(cfg.get("storage_encrypted")),
        "broker storage encrypted at rest"
        if cfg.get("storage_encrypted")
        else "broker storage is not encrypted",
    ))
    checks.append(_check(
        "kafka-tls-in-transit",
        cfg.get("tls_in_transit") in ("required", True),
        "TLS required for client traffic"
        if cfg.get("tls_in_transit") in ("required", True)
        else "TLS is not required for client traffic",
    ))
    checks.append(_check(
        "kafka-version-pinned",
        bool(cfg.get("version")),
        f"Kafka version {cfg.get('version')} pinned"
        if cfg.get("version")
        else "Kafka version is not pinned",
    ))
    return checks


def check_rds_aurora(cfg):
    """Validate an RDS Aurora cluster config dict."""
    checks = []
    engine = str(cfg.get("engine", ""))
    checks.append(_check(
        "aurora-engine",
        engine.startswith("aurora-"),
        f"engine {engine or 'not set'} (expected aurora-postgresql or "
        f"aurora-mysql)",
    ))
    checks.append(_check(
        "aurora-backup-retention",
        cfg.get("backup_retention_days", 0) >= MIN_BACKUP_RETENTION_DAYS,
        f"backup retention {cfg.get('backup_retention_days', 0)} day(s) "
        f"(minimum {MIN_BACKUP_RETENTION_DAYS})",
    ))
    checks.append(_check(
        "aurora-multi-az",
        cfg.get("instance_count", 0) >= 2,
        f"{cfg.get('instance_count', 0)} DB instance(s) across AZs "
        f"(minimum 2)",
    ))
    checks.append(_check(
        "aurora-storage-encrypted",
        bool(cfg.get("storage_encrypted")),
        "cluster storage encrypted"
        if cfg.get("storage_encrypted")
        else "cluster storage is not encrypted",
    ))
    checks.append(_check(
        "aurora-deletion-protection",
        bool(cfg.get("deletion_protection")),
        "deletion protection enabled"
        if cfg.get("deletion_protection")
        else "deletion protection is off",
    ))
    return checks


def check_cloud_foundation(cfg):
    """Validate Cloud Foundation stack guardrails: tags, ingress, SSO."""
    checks = []
    stacks = cfg.get("stacks", [])
    missing = sorted({
        tag
        for stack in stacks
        for tag in REQUIRED_TAGS
        if tag not in stack.get("tags", {})
    })
    checks.append(_check(
        "foundation-required-tags",
        not missing and bool(stacks),
        f"required tags {', '.join(REQUIRED_TAGS)} present on all stacks"
        if not missing and stacks
        else f"missing required tag(s): {', '.join(missing) or 'no stacks'}",
    ))
    open_rules = [
        rule.get("name", "unnamed")
        for stack in stacks
        for rule in stack.get("ingress_rules", [])
        if rule.get("cidr") == "0.0.0.0/0"
    ]
    checks.append(_check(
        "foundation-no-public-ingress",
        not open_rules,
        "no security-group ingress open to 0.0.0.0/0"
        if not open_rules
        else f"public ingress open on: {', '.join(open_rules)}",
    ))
    checks.append(_check(
        "foundation-sso-federation",
        bool(cfg.get("sso_enabled")),
        "SSO / federation configured for console and CLI access"
        if cfg.get("sso_enabled")
        else "SSO / federation is not configured",
    ))
    checks.append(_check(
        "foundation-cloudtrail-enabled",
        bool(cfg.get("cloudtrail_enabled")),
        "CloudTrail logging enabled in all regions"
        if cfg.get("cloudtrail_enabled")
        else "CloudTrail logging is not enabled",
    ))
    return checks


def check_storage_backup(cfg):
    """Validate storage and backup settings for a platform config."""
    checks = []
    checks.append(_check(
        "backup-plan-present",
        bool(cfg.get("backup_plan")),
        f"backup plan '{cfg.get('backup_plan')}' configured"
        if cfg.get("backup_plan")
        else "no backup plan configured",
    ))
    checks.append(_check(
        "backup-retention",
        cfg.get("retention_days", 0) >= MIN_STORAGE_BACKUP_RETENTION_DAYS,
        f"backup retention {cfg.get('retention_days', 0)} day(s) "
        f"(minimum {MIN_STORAGE_BACKUP_RETENTION_DAYS})",
    ))
    checks.append(_check(
        "backup-vault-encrypted",
        bool(cfg.get("vault_encrypted")),
        "backup vault encrypted"
        if cfg.get("vault_encrypted")
        else "backup vault is not encrypted",
    ))
    checks.append(_check(
        "backup-recent-success",
        cfg.get("hours_since_last_success", 999) <= 24,
        f"last successful backup "
        f"{cfg.get('hours_since_last_success', 'unknown')} hour(s) ago "
        f"(limit 24)",
    ))
    checks.append(_check(
        "storage-lifecycle-cold",
        bool(cfg.get("lifecycle_to_cold")),
        "lifecycle rule moves old objects to cold storage"
        if cfg.get("lifecycle_to_cold")
        else "no lifecycle rule to cold storage",
    ))
    return checks


def platform_report(checks):
    """Summarize a list of checks: overall status plus pass/fail counts."""
    failed = [c for c in checks if c["status"] != "pass"]
    return {
        "overall": "fail" if failed else "pass",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_checks": [c["name"] for c in failed],
    }


def demo_config():
    """A demo platform config with a few deliberate failures: EKS
    logging off, Kafka replication too low, one stack missing a tag."""
    return {
        "eks": {
            "version": "1.30",
            "node_groups": [
                {"name": "general", "zones": ["us-east-1a", "us-east-1b"],
                 "min_size": 2},
            ],
            "control_plane_logging": False,
            "secrets_encryption": True,
            "endpoint_public_access": False,
        },
        "kafka": {
            "broker_count": 3,
            "default_replication_factor": 2,
            "min_insync_replicas": 2,
            "storage_encrypted": True,
            "tls_in_transit": "required",
            "version": "3.7.0",
        },
        "aurora": {
            "engine": "aurora-postgresql",
            "backup_retention_days": 14,
            "instance_count": 2,
            "storage_encrypted": True,
            "deletion_protection": True,
        },
        "foundation": {
            "stacks": [
                {"name": "network",
                 "tags": {"owner": "platform", "environment": "prod",
                          "cost-center": "eng"},
                 "ingress_rules": [{"name": "ssh-bastion",
                                    "cidr": "10.0.0.0/16"}]},
                {"name": "data",
                 "tags": {"owner": "platform", "environment": "prod"},
                 "ingress_rules": []},
            ],
            "sso_enabled": True,
            "cloudtrail_enabled": True,
        },
        "storage_backup": {
            "backup_plan": "daily-platform",
            "retention_days": 35,
            "vault_encrypted": True,
            "hours_since_last_success": 5,
            "lifecycle_to_cold": True,
        },
    }


def check_platform(config):
    """Run every platform check group and return the flat check list."""
    checks = []
    checks += check_eks_cluster(config.get("eks", {}))
    checks += check_kafka_cluster(config.get("kafka", {}))
    checks += check_rds_aurora(config.get("aurora", {}))
    checks += check_cloud_foundation(config.get("foundation", {}))
    checks += check_storage_backup(config.get("storage_backup", {}))
    return checks


def main():
    checks = check_platform(demo_config())
    for check in checks:
        print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
    report = platform_report(checks)
    print(
        f"overall={report['overall']} passed={report['passed']} "
        f"failed={report['failed']} "
        f"failed_checks={', '.join(report['failed_checks'])}"
    )


if __name__ == "__main__":
    main()
