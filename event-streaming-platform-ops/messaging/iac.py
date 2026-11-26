"""Infrastructure-as-Code validation for the messaging platform.

The manifests in ``iac/`` are declarative desired-state documents
(Terraform, Ansible, Chef). Nothing here calls AWS, Chef or Ansible:
this module loads the YAML manifests and checks them against the
platform's own standards — replication across AZs, encryption at rest,
retention bounds, and required runbook references — so a bad change
fails in CI before it ever reaches a real apply.
"""

from __future__ import annotations

import re

import yaml

MIN_REPLICATION = 3
MIN_RETENTION_HOURS = 24
MAX_RETENTION_HOURS = 8760  # 1 year
REQUIRED_ZONES = 3


class ManifestError(ValueError):
    pass


def load_yaml_manifest(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: manifest must be a YAML mapping")
    return data


def validate_topic(topic: dict, name: str = "?") -> list[str]:
    errors = []
    partitions = topic.get("partitions")
    if not isinstance(partitions, int) or partitions < 1:
        errors.append(f"topic {name}: partitions must be a positive integer")
    replication = topic.get("replication_factor")
    if not isinstance(replication, int) or replication < MIN_REPLICATION:
        errors.append(f"topic {name}: replication_factor must be >= "
                      f"{MIN_REPLICATION}")
    retention = topic.get("retention_hours")
    if not isinstance(retention, int) or not (
            MIN_RETENTION_HOURS <= retention <= MAX_RETENTION_HOURS):
        errors.append(f"topic {name}: retention_hours must be between "
                      f"{MIN_RETENTION_HOURS} and {MAX_RETENTION_HOURS}")
    zones = topic.get("availability_zones") or []
    if len(set(zones)) < REQUIRED_ZONES:
        errors.append(f"topic {name}: replicas must span at least "
                      f"{REQUIRED_ZONES} availability zones")
    if topic.get("encryption_at_rest") is not True:
        errors.append(f"topic {name}: encryption_at_rest must be true")
    return errors


def validate_queue(queue: dict, name: str = "?") -> list[str]:
    errors = []
    if queue.get("visibility_timeout_seconds", 0) < 30:
        errors.append(f"queue {name}: visibility_timeout_seconds must be "
                      f">= 30")
    if not queue.get("dead_letter_queue"):
        errors.append(f"queue {name}: a dead_letter_queue is required")
    if queue.get("encryption_at_rest") is not True:
        errors.append(f"queue {name}: encryption_at_rest must be true")
    return errors


def validate_platform_manifest(manifest: dict) -> list[str]:
    """Validate a whole platform manifest; returns a list of errors."""
    errors = []
    cluster = manifest.get("cluster")
    if not isinstance(cluster, dict):
        return ["manifest: missing 'cluster' mapping"]
    brokers = cluster.get("brokers") or []
    if len(brokers) < MIN_REPLICATION:
        errors.append("cluster: need at least 3 brokers")
    zones = {b.get("availability_zone") for b in brokers
             if isinstance(b, dict)}
    if len(zones) < REQUIRED_ZONES:
        errors.append("cluster: brokers must span at least 3 availability "
                      "zones")
    for topic in manifest.get("topics") or []:
        errors += validate_topic(topic, topic.get("name", "?"))
    for queue in manifest.get("queues") or []:
        errors += validate_queue(queue, queue.get("name", "?"))
    return errors


def check_ansible_playbook(path: str) -> list[str]:
    """Lightweight checks on the Ansible playbook YAML."""
    errors = []
    try:
        plays = yaml.safe_load(open(path, encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]
    if not isinstance(plays, list) or not plays:
        return [f"{path}: playbook must be a non-empty list of plays"]
    for play in plays:
        tasks = play.get("tasks") or []
        if not tasks:
            errors.append(f"play {play.get('name', '?')}: no tasks")
        for task in tasks:
            if "name" not in task:
                errors.append("playbook: every task needs a name")
    return errors


def check_chef_recipe(path: str) -> list[str]:
    """Lightweight checks on the Chef recipe text."""
    text = open(path, encoding="utf-8").read()
    errors = []
    for resource in ("package", "service", "template", "directory"):
        if not re.search(rf"^{resource}\b", text, re.MULTILINE):
            errors.append(f"recipe: missing {resource!r} resource")
    if "notifies" not in text:
        errors.append("recipe: service should be notified on config change")
    return errors
