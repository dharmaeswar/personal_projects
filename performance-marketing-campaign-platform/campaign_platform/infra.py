"""Infrastructure as code: Terraform configuration for the AWS footprint.

The pipeline runs on AWS with Databricks for Spark and Snowflake for
warehousing. This module generates the Terraform that provisions that
footprint (S3 buckets, Glue job, Databricks workspace, Snowflake external
stage) from one environment definition, so staging and production differ
only by variables — never by hand-edited resources.

The generated HCL is a configuration document, not an applied plan:
nothing is provisioned by running this project.
"""

from __future__ import annotations

import json


def terraform_config(env: str, region: str = "us-east-1") -> dict:
    """Resource definition for one environment (dev / staging / prod)."""
    if env not in ("dev", "staging", "prod"):
        raise ValueError("env must be dev, staging or prod")
    prefix = f"perf-marketing-{env}"
    return {
        "terraform": {"required_version": ">= 1.5.0"},
        "provider": {"aws": {"region": region}},
        "resource": {
            "aws_s3_bucket": {
                "bronze": {"bucket": f"{prefix}-bronze", "force_destroy": env != "prod"},
                "silver": {"bucket": f"{prefix}-silver", "force_destroy": env != "prod"},
                "gold": {"bucket": f"{prefix}-gold", "force_destroy": env != "prod"},
            },
            "aws_glue_job": {
                "ingest": {"name": f"{prefix}-ingest", "role_arn": "var.glue_role_arn",
                           "glue_version": "4.0", "worker_type": "G.1X",
                           "number_of_workers": 5 if env == "prod" else 2},
            },
            "databricks_workspace": {
                "main": {"name": f"{prefix}-workspace",
                         "sku": "premium" if env == "prod" else "standard"},
            },
            "snowflake_stage": {
                "gold": {"name": f"{prefix}_gold_stage",
                         "url": f"s3://{prefix}-gold/",
                         "storage_integration": "var.snowflake_storage_integration"},
            },
        },
        "output": {
            "bronze_bucket": {"value": f"${{aws_s3_bucket.bronze.bucket}}"},
            "gold_bucket": {"value": f"${{aws_s3_bucket.gold.bucket}}"},
        },
    }


def render_main_tf(config: dict) -> str:
    """Render the resource definition as HCL text (main.tf)."""
    lines = [
        f'terraform {{\n  required_version = "{config["terraform"]["required_version"]}"\n}}\n',
        f'provider "aws" {{\n  region = "{config["provider"]["aws"]["region"]}"\n}}\n',
    ]
    for resource_type, resources in config["resource"].items():
        for name, attrs in resources.items():
            lines.append(f'resource "{resource_type}" "{name}" {{')
            for key, value in attrs.items():
                rendered = json.dumps(value)
                lines.append(f"  {key} = {rendered}")
            lines.append("}\n")
    for name, output in config["output"].items():
        lines.append(f'output "{name}" {{')
        lines.append(f'  value = {json.dumps(output["value"])}')
        lines.append("}\n")
    return "\n".join(lines)
