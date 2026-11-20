"""Multi-cloud infrastructure-as-code checks for the Platform Ops
Automation demo project.

Validates a Terraform-style plan summary (plain dicts, no real cloud
calls), audits secret rotation freshness, and estimates cross-cloud
data-transfer cost so the cheapest resilient path can be picked.
All inputs are demo data — no real infrastructure is described, and
no real cloud account is touched.
"""

from datetime import date


def _parse(value):
    if isinstance(value, date):
        return value
    year, month, day = (int(part) for part in value.split("-"))
    return date(year, month, day)


def check_plan(plan):
    """Validate a plan summary. `plan` is a dict with a `resources` list;
    each resource has `cloud` ("aws"/"azure"/"gcp"), `type`, `tags`
    (dict), `public_ingress` (bool), and `secret_ref` ("vault" or
    "plaintext"). Returns a list of check dicts with `name`, `status`
    ("pass"/"fail"), and `detail`."""
    checks = []
    resources = plan.get("resources", [])
    untagged = [r["type"] for r in resources if not r.get("tags")]
    checks.append(
        {
            "name": "all-resources-tagged",
            "status": "pass" if not untagged else "fail",
            "detail": (
                "all resources tagged"
                if not untagged
                else f"untagged resources: {', '.join(untagged)}"
            ),
        }
    )
    open_ingress = [r["type"] for r in resources if r.get("public_ingress")]
    checks.append(
        {
            "name": "no-open-ingress",
            "status": "pass" if not open_ingress else "fail",
            "detail": (
                "no public ingress rules"
                if not open_ingress
                else f"open ingress on: {', '.join(open_ingress)}"
            ),
        }
    )
    plaintext = [r["type"] for r in resources if r.get("secret_ref") == "plaintext"]
    checks.append(
        {
            "name": "secrets-via-vault",
            "status": "pass" if not plaintext else "fail",
            "detail": (
                "all secrets referenced via Vault"
                if not plaintext
                else f"plaintext secrets in: {', '.join(plaintext)}"
            ),
        }
    )
    clouds = sorted({r["cloud"] for r in resources})
    checks.append(
        {
            "name": "multi-cloud-redundancy",
            "status": "pass" if len(clouds) >= 2 else "fail",
            "detail": f"plan spans {len(clouds)} cloud(s): {', '.join(clouds)}",
        }
    )
    return checks


def check_secrets(secrets, today, max_age_days=90):
    """Audit secret rotation. Each secret has `name` and `last_rotated`
    (ISO date). Returns a check dict per secret."""
    checks = []
    for secret in secrets:
        age = (today - _parse(secret["last_rotated"])).days
        checks.append(
            {
                "name": f"secret-rotated:{secret['name']}",
                "status": "pass" if age <= max_age_days else "fail",
                "detail": f"{secret['name']} rotated {age} days ago "
                f"(limit {max_age_days})",
            }
        )
    return checks


def estimate_transfer_cost(gigabytes, rates_per_gb):
    """Estimate cross-cloud transfer cost. `rates_per_gb` maps a
    cloud-pair label (e.g. "aws-to-gcp") to a dollars-per-GB rate.
    Returns a dict with the per-path costs and the cheapest path."""
    costs = {
        path: round(gigabytes * rate, 2) for path, rate in rates_per_gb.items()
    }
    cheapest = min(costs, key=costs.get) if costs else None
    return {"gigabytes": gigabytes, "costs": costs, "cheapest": cheapest}


def iac_report(plan_checks, secret_checks):
    """Summarize plan + secret checks: overall status plus counts."""
    all_checks = list(plan_checks) + list(secret_checks)
    failed = [c for c in all_checks if c["status"] != "pass"]
    return {
        "overall": "fail" if failed else "pass",
        "passed": len(all_checks) - len(failed),
        "failed": len(failed),
        "failed_checks": [c["name"] for c in failed],
    }


def demo_plan():
    """A demo plan with two faults: one untagged resource and one
    plaintext secret reference."""
    return {
        "resources": [
            {
                "cloud": "aws",
                "type": "aws_eks_cluster",
                "tags": {"env": "prod", "team": "platform"},
                "public_ingress": False,
                "secret_ref": "vault",
            },
            {
                "cloud": "aws",
                "type": "aws_s3_bucket",
                "tags": {},
                "public_ingress": False,
                "secret_ref": "vault",
            },
            {
                "cloud": "gcp",
                "type": "google_compute_instance",
                "tags": {"env": "prod", "team": "platform"},
                "public_ingress": False,
                "secret_ref": "plaintext",
            },
        ]
    }


def demo_secrets():
    """Demo secrets: one rotated recently, one stale (121 days)."""
    return [
        {"name": "db-password", "last_rotated": "2026-11-10"},
        {"name": "api-key", "last_rotated": "2026-07-22"},
    ]


def main():
    today = date(2026, 11, 20)
    plan_checks = check_plan(demo_plan())
    secret_checks = check_secrets(demo_secrets(), today)
    for check in plan_checks + secret_checks:
        print(f"[{check['status'].upper()}] {check['name']}: {check['detail']}")
    report = iac_report(plan_checks, secret_checks)
    print(
        f"overall={report['overall']} passed={report['passed']} "
        f"failed={report['failed']}"
    )
    cost = estimate_transfer_cost(
        500, {"aws-to-gcp": 0.09, "aws-to-azure": 0.08, "gcp-to-azure": 0.07}
    )
    print(f"transfer 500GB costs={cost['costs']} cheapest={cost['cheapest']}")


if __name__ == "__main__":
    main()
