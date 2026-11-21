"""Demo: run a partner request through the full platform.

Seeds a skill registry, a knowledge base, one data product and one model,
then handles a partner question end to end: skill approval, knowledge
retrieval, scoped data vending, and a live-model check. Prints a short
report with the audit trail. All data is synthetic.
"""

from __future__ import annotations

import json

from partner_platform.agent import PartnerAgent
from partner_platform.knowledge import KnowledgeBase
from partner_platform.models import ModelPlatform, ModelVersion
from partner_platform.skills import Skill, SkillRegistry
from partner_platform.vending import DataProduct, DataVending, Token


def build_platform() -> PartnerAgent:
    skills = SkillRegistry()
    skills.register(Skill(
        name="campaign_insights",
        version="1.2.0",
        description="Summarize campaign performance for an ads partner.",
        input_schema={"campaign_id": "string", "date_range": "string"},
        required_scopes=["campaigns:read"],
        risk="low",
    ))
    skills.register(Skill(
        name="audience_export",
        version="1.0.0",
        description="Export an audience segment for activation by a partner.",
        input_schema={"segment_id": "string", "destination": "string"},
        required_scopes=["audiences:read", "sensitive:read"],
        risk="high",
    ))

    knowledge = KnowledgeBase()
    knowledge.add_document(
        "partner-guide-001", "Partner Campaign Guide",
        "Campaign insights summarize impressions, clicks and spend by campaign "
        "and channel. Partners can request daily breakdowns and compare "
        "performance across channels. Audience exports move a segment to an "
        "activation destination and always require a human approval first.",
        fresh_until="2027-01-01",
    )

    vending = DataVending()
    vending.register(DataProduct(
        product_id="campaign-performance",
        name="Campaign Performance Daily",
        owner="ads-partner-data",
        required_scopes=["campaigns:read"],
        columns=["campaign_id", "date", "impressions", "clicks", "spend_usd",
                 "advertiser_email"],
        sensitive_columns=["advertiser_email"],
        rows=[
            {"campaign_id": "cmp-101", "date": "2026-11-20", "impressions": 12000,
             "clicks": 340, "spend_usd": 412.50,
             "advertiser_email": "partner@example.com"},
            {"campaign_id": "cmp-102", "date": "2026-11-20", "impressions": 8400,
             "clicks": 210, "spend_usd": 268.00,
             "advertiser_email": "partner2@example.com"},
        ],
    ))

    models = ModelPlatform()
    models.register(ModelVersion(
        model_name="spend-forecast",
        version="2.1.0",
        owner="ads-ml",
        tests_passed=True,
        eval_metrics={"mape": 0.08, "coverage": 0.92},
        rollback_plan={"version": "2.0.0", "steps": ["drain traffic", "restore 2.0.0"]},
        on_call_primary="ads-ml-oncall",
        on_call_backup="ads-ml-backup",
        deploy_window="09:00-17:00 ET weekdays",
    ))
    models.launch("spend-forecast", "2.1.0")

    return PartnerAgent(skills, knowledge, vending, models)


def main() -> None:
    agent = build_platform()
    token = Token(token_id="tok-demo-1", holder="partner-app",
                  scopes=["campaigns:read"], expires="2027-06-01")
    outcome = agent.handle_request(
        intent="campaign_insights",
        question="How do I read campaign insights by channel?",
        token=token,
        skill_inputs={"campaign_id": "cmp-101", "date_range": "2026-11-20"},
        product_id="campaign-performance",
        model_name="spend-forecast",
    )
    print(json.dumps(outcome, indent=2))


if __name__ == "__main__":
    main()
