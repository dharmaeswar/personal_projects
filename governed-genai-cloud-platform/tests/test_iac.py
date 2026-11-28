from genai_platform.iac import (
    ComputeRuntime,
    DataStore,
    IamPolicy,
    IamRole,
    PlatformPlan,
    Subnet,
    demo_plan,
)


def test_demo_plan_passes_validation():
    assert demo_plan().validate() == []


def test_missing_tag_is_a_violation():
    plan = demo_plan()
    plan.tags.pop("owner")
    assert any("missing required tag: owner" in v for v in plan.validate())


def test_public_data_subnet_is_a_violation():
    plan = demo_plan()
    plan.subnets.append(Subnet("data-c", "10.20.13.0/24", True, "us-east-1a"))
    assert any("must not be public" in v for v in plan.validate())


def test_wildcard_iam_action_is_a_violation():
    plan = demo_plan()
    plan.roles[0].policies.append(
        IamPolicy("bad", ["s3:*"], ["arn:aws:s3:::genai-kb-nonprod/*"])
    )
    assert any("forbids action s3:*" in v for v in plan.validate())


def test_unencrypted_store_is_a_violation():
    plan = demo_plan()
    plan.stores.append(
        DataStore("raw", "genai-raw", False, True, True, "internal")
    )
    assert any("not encrypted at rest" in v for v in plan.validate())


def test_role_without_policies_is_a_violation():
    plan = demo_plan()
    plan.roles.append(IamRole("empty-role", "ec2.amazonaws.com"))
    assert any("has no policies" in v for v in plan.validate())


def test_eks_runtime_without_subnets_is_a_violation():
    plan = demo_plan()
    plan.runtimes.append(
        ComputeRuntime("orphan", "eks", "img:1", "500m", 512, 1, 2)
    )
    assert any("no subnets assigned" in v for v in plan.validate())


def test_summary_counts():
    summary = demo_plan().summary()
    assert summary["subnets"] == 4
    assert summary["roles"] == 2
    assert summary["bedrock_models"] == 3
    assert summary["violations"] == 0
