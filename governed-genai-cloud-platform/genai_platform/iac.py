"""Terraform-style infrastructure-as-code definitions for the governed GenAI
platform on AWS, plus plan validation.

The platform is defined as plain Python data (the same shape a Terraform
plan would carry): VPC and subnets, IAM roles with least-privilege policies,
compute runtimes (EKS node groups and Lambda functions), S3 data stores and
Bedrock model access. ``validate_plan`` enforces the guardrails the bank
runs as code: no public data subnets, no wildcard IAM actions, encryption
at rest, and mandatory cost/owner tags.

All resources are definitions only — nothing here contacts AWS, creates
real infrastructure, or spends money. A real Terraform adapter renders
these definitions to ``.tf`` files; the validation rules are the same
either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REQUIRED_TAGS = ("owner", "cost-center", "environment", "data-classification")

# IAM actions that are never allowed in a platform policy: wildcards and
# privilege-escalation actions a least-privilege review rejects outright.
FORBIDDEN_ACTIONS = {
    "*",
    "iam:*",
    "iam:PassRole",
    "iam:CreateUser",
    "iam:AttachUserPolicy",
    "s3:DeleteBucket",
    "kms:DisableKey",
}


@dataclass
class IamPolicy:
    """One IAM policy statement set attached to a role."""

    name: str
    actions: list[str]
    resources: list[str]

    def forbidden_actions(self) -> list[str]:
        """Actions in this policy that the guardrail forbids."""
        bad = []
        for action in self.actions:
            if action in FORBIDDEN_ACTIONS or action.endswith(":*"):
                bad.append(action)
        return bad


@dataclass
class IamRole:
    """An IAM role with a trust principal and attached policies."""

    name: str
    trusted_service: str
    policies: list[IamPolicy] = field(default_factory=list)

    def all_actions(self) -> list[str]:
        return [a for p in self.policies for a in p.actions]


@dataclass
class Subnet:
    name: str
    cidr: str
    public: bool
    az: str


@dataclass
class DataStore:
    """An S3-backed data store (knowledge base, audit log, eval results)."""

    name: str
    bucket: str
    encrypted: bool
    versioned: bool
    public_access_blocked: bool
    data_classification: str


@dataclass
class ComputeRuntime:
    """A compute runtime: EKS node group or Lambda function."""

    name: str
    kind: str  # "eks" or "lambda"
    image: str
    cpu: str
    memory_mb: int
    min_replicas: int
    max_replicas: int
    subnets: list[str] = field(default_factory=list)


@dataclass
class PlatformPlan:
    """The whole platform definition, as a Terraform plan would describe it."""

    environment: str
    region: str
    vpc_cidr: str
    subnets: list[Subnet] = field(default_factory=list)
    roles: list[IamRole] = field(default_factory=list)
    runtimes: list[ComputeRuntime] = field(default_factory=list)
    stores: list[DataStore] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    bedrock_models: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Return a list of guardrail violations; empty means the plan passes."""
        problems: list[str] = []
        for tag in REQUIRED_TAGS:
            if tag not in self.tags or not str(self.tags[tag]).strip():
                problems.append(f"missing required tag: {tag}")
        for subnet in self.subnets:
            if subnet.public and subnet.name.startswith("data"):
                problems.append(
                    f"data subnet {subnet.name} must not be public"
                )
        for role in self.roles:
            for policy in role.policies:
                for action in policy.forbidden_actions():
                    problems.append(
                        f"role {role.name} policy {policy.name} "
                        f"forbids action {action}"
                    )
            if not role.policies:
                problems.append(f"role {role.name} has no policies attached")
        for store in self.stores:
            if not store.encrypted:
                problems.append(f"data store {store.name} is not encrypted at rest")
            if not store.versioned:
                problems.append(f"data store {store.name} is not versioned")
            if not store.public_access_blocked:
                problems.append(
                    f"data store {store.name} does not block public access"
                )
        for runtime in self.runtimes:
            if runtime.min_replicas < 1:
                problems.append(
                    f"runtime {runtime.name} must run at least 1 replica"
                )
            if runtime.max_replicas < runtime.min_replicas:
                problems.append(
                    f"runtime {runtime.name} max replicas below min replicas"
                )
            if runtime.kind == "eks" and not runtime.subnets:
                problems.append(
                    f"EKS runtime {runtime.name} has no subnets assigned"
                )
        if not self.bedrock_models:
            problems.append("no Bedrock models are enabled for the gateway")
        return problems

    def summary(self) -> dict:
        """Counts for the platform report."""
        return {
            "environment": self.environment,
            "region": self.region,
            "subnets": len(self.subnets),
            "roles": len(self.roles),
            "runtimes": len(self.runtimes),
            "stores": len(self.stores),
            "bedrock_models": len(self.bedrock_models),
            "violations": len(self.validate()),
        }


def demo_plan() -> PlatformPlan:
    """A passing reference plan for the bank's non-production environment."""
    return PlatformPlan(
        environment="nonprod",
        region="us-east-1",
        vpc_cidr="10.20.0.0/16",
        subnets=[
            Subnet("app-a", "10.20.1.0/24", public=False, az="us-east-1a"),
            Subnet("app-b", "10.20.2.0/24", public=False, az="us-east-1b"),
            Subnet("data-a", "10.20.11.0/24", public=False, az="us-east-1a"),
            Subnet("data-b", "10.20.12.0/24", public=False, az="us-east-1b"),
        ],
        roles=[
            IamRole(
                name="genai-gateway-role",
                trusted_service="ecs-tasks.amazonaws.com",
                policies=[
                    IamPolicy(
                        name="bedrock-invoke",
                        actions=[
                            "bedrock:InvokeModel",
                            "bedrock:InvokeModelWithResponseStream",
                        ],
                        resources=[
                            "arn:aws:bedrock:us-east-1::foundation-model/*"
                        ],
                    ),
                    IamPolicy(
                        name="kb-read",
                        actions=["s3:GetObject", "s3:ListBucket"],
                        resources=["arn:aws:s3:::genai-kb-nonprod/*"],
                    ),
                ],
            ),
            IamRole(
                name="genai-agent-role",
                trusted_service="lambda.amazonaws.com",
                policies=[
                    IamPolicy(
                        name="agent-tools",
                        actions=[
                            "dynamodb:GetItem",
                            "dynamodb:Query",
                            "s3:GetObject",
                        ],
                        resources=["arn:aws:dynamodb:us-east-1:*:table/agent-*"],
                    )
                ],
            ),
        ],
        runtimes=[
            ComputeRuntime(
                name="gateway-api",
                kind="eks",
                image="genai/gateway:1.4.0",
                cpu="500m",
                memory_mb=1024,
                min_replicas=2,
                max_replicas=8,
                subnets=["app-a", "app-b"],
            ),
            ComputeRuntime(
                name="agent-runner",
                kind="lambda",
                image="genai/agent-runner:1.4.0",
                cpu="1024m",
                memory_mb=2048,
                min_replicas=1,
                max_replicas=20,
            ),
        ],
        stores=[
            DataStore(
                name="knowledge-base",
                bucket="genai-kb-nonprod",
                encrypted=True,
                versioned=True,
                public_access_blocked=True,
                data_classification="confidential",
            ),
            DataStore(
                name="audit-log",
                bucket="genai-audit-nonprod",
                encrypted=True,
                versioned=True,
                public_access_blocked=True,
                data_classification="confidential",
            ),
        ],
        tags={
            "owner": "cloud-platform",
            "cost-center": "CC-4100",
            "environment": "nonprod",
            "data-classification": "confidential",
        },
        bedrock_models=[
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "amazon.titan-text-premier-v1:0",
            "meta.llama3-70b-instruct-v1:0",
        ],
    )
