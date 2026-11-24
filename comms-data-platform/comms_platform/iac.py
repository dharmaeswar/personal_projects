"""Infrastructure as code — a local model of the AWS CDK stack.

The real platform is defined in CDK (TypeScript). This module builds the
same stack as a declarative manifest: S3 buckets for the lake layers,
Glue jobs, a Step Functions state machine, Lambda functions, a DynamoDB
serving cache, an Athena workgroup and CloudWatch alarms. `validate_stack`
checks the manifest the way a CDK synth + `cdk diff` review would: every
resource has a type and required properties, and every referenced resource
exists.
"""

from __future__ import annotations

import json

REQUIRED_PROPS = {
    "AWS::S3::Bucket": ["BucketName"],
    "AWS::Glue::Job": ["Name", "RoleArn"],
    "AWS::StepFunctions::StateMachine": ["DefinitionString"],
    "AWS::Lambda::Function": ["FunctionName", "Handler", "Runtime"],
    "AWS::DynamoDB::Table": ["TableName", "KeySchema"],
    "AWS::Athena::WorkGroup": ["Name"],
    "AWS::CloudWatch::Alarm": ["AlarmName", "MetricName", "Threshold"],
}


def build_stack(environment="dev"):
    """Return the CDK-style stack manifest for one environment."""
    prefix = f"comms-data-{environment}"
    return {
        "StackName": f"{prefix}-stack",
        "Environment": environment,
        "Resources": {
            "BronzeBucket": {
                "Type": "AWS::S3::Bucket",
                "Properties": {"BucketName": f"{prefix}-bronze"},
            },
            "SilverBucket": {
                "Type": "AWS::S3::Bucket",
                "Properties": {"BucketName": f"{prefix}-silver"},
            },
            "GoldBucket": {
                "Type": "AWS::S3::Bucket",
                "Properties": {"BucketName": f"{prefix}-gold"},
            },
            "IngestJob": {
                "Type": "AWS::Glue::Job",
                "Properties": {
                    "Name": f"{prefix}-ingest",
                    "RoleArn": "arn:aws:iam::123456789012:role/GlueServiceRole",
                    "GlueVersion": "4.0",
                },
            },
            "TransformJob": {
                "Type": "AWS::Glue::Job",
                "Properties": {
                    "Name": f"{prefix}-transform",
                    "RoleArn": "arn:aws:iam::123456789012:role/GlueServiceRole",
                    "GlueVersion": "4.0",
                },
            },
            "PipelineStateMachine": {
                "Type": "AWS::StepFunctions::StateMachine",
                "Properties": {
                    "DefinitionString": json.dumps(
                        {
                            "StartAt": "Ingest",
                            "States": {
                                "Ingest": {"Type": "Task", "Next": "Validate"},
                                "Validate": {"Type": "Task", "Next": "Transform"},
                                "Transform": {"Type": "Task", "Next": "Catalog"},
                                "Catalog": {"Type": "Task", "End": True},
                            },
                        }
                    )
                },
            },
            "ServingApiFunction": {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "FunctionName": f"{prefix}-serving-api",
                    "Handler": "serving.handler",
                    "Runtime": "python3.12",
                },
            },
            "McpToolFunction": {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "FunctionName": f"{prefix}-mcp-tools",
                    "Handler": "serving.mcp_handler",
                    "Runtime": "python3.12",
                },
            },
            "ServingCache": {
                "Type": "AWS::DynamoDB::Table",
                "Properties": {
                    "TableName": f"{prefix}-serving-cache",
                    "KeySchema": [{"AttributeName": "dataset", "KeyType": "HASH"}],
                },
            },
            "AnalyticsWorkGroup": {
                "Type": "AWS::Athena::WorkGroup",
                "Properties": {"Name": f"{prefix}-analytics"},
            },
            "PipelineFailureAlarm": {
                "Type": "AWS::CloudWatch::Alarm",
                "Properties": {
                    "AlarmName": f"{prefix}-pipeline-failures",
                    "MetricName": "PipelineFailures",
                    "Threshold": 1,
                },
            },
            "FreshnessAlarm": {
                "Type": "AWS::CloudWatch::Alarm",
                "Properties": {
                    "AlarmName": f"{prefix}-gold-freshness",
                    "MetricName": "GoldTableAgeHours",
                    "Threshold": 26,
                },
            },
        },
    }


def validate_stack(stack):
    """Check the manifest; return a list of problems (empty when valid)."""
    problems = []
    resources = stack.get("Resources", {})
    if not stack.get("StackName"):
        problems.append("stack has no StackName")
    for logical_id, resource in resources.items():
        rtype = resource.get("Type")
        if rtype not in REQUIRED_PROPS:
            problems.append(f"{logical_id}: unknown resource type {rtype}")
            continue
        for prop in REQUIRED_PROPS[rtype]:
            if prop not in resource.get("Properties", {}):
                problems.append(f"{logical_id}: missing required property {prop}")
    expected = {
        "BronzeBucket",
        "SilverBucket",
        "GoldBucket",
        "IngestJob",
        "TransformJob",
        "PipelineStateMachine",
        "ServingApiFunction",
        "McpToolFunction",
        "ServingCache",
        "AnalyticsWorkGroup",
        "PipelineFailureAlarm",
        "FreshnessAlarm",
    }
    missing = expected - set(resources)
    if missing:
        problems.append(f"missing resources: {sorted(missing)}")
    return problems


def write_manifest(stack, path):
    Path = __import__("pathlib").Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(stack, indent=2))
    return p
