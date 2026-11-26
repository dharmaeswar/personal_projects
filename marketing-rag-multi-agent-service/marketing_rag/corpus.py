"""Seeded synthetic marketing corpus: campaigns, segments, content assets,
and CRM-like contacts. All data is invented and generated locally with a
fixed seed. No real customers, campaigns, or performance figures are used.
"""
from __future__ import annotations

import random

SEED = 42

CAMPAIGNS = [
    {"id": "CMP-001", "name": "Spring Launch Email", "channel": "email",
     "spend": 42000, "leads": 1850, "conversions": 296, "revenue": 148000,
     "audience": "mid-market ops leaders", "status": "completed",
     "notes": "Welcome series plus product launch announcement; best open rate of the quarter."},
    {"id": "CMP-002", "name": "Paid Search Brand Core", "channel": "paid search",
     "spend": 68000, "leads": 2400, "conversions": 384, "revenue": 211200,
     "audience": "high-intent searchers", "status": "active",
     "notes": "Brand and competitor conquesting terms; capped daily budget."},
    {"id": "CMP-003", "name": "LinkedIn ABM Pilot", "channel": "paid social",
     "spend": 55000, "leads": 940, "conversions": 141, "revenue": 112800,
     "audience": "enterprise marketing VPs", "status": "active",
     "notes": "Account-based pilot on 400 target accounts; sponsored content plus InMail."},
    {"id": "CMP-004", "name": "Webinar Series Q2", "channel": "webinar",
     "spend": 18000, "leads": 1250, "conversions": 175, "revenue": 87500,
     "audience": "marketing practitioners", "status": "completed",
     "notes": "Four live sessions with on-demand replay; co-hosted with a partner."},
    {"id": "CMP-005", "name": "Display Retargeting", "channel": "display",
     "spend": 31000, "leads": 720, "conversions": 58, "revenue": 29000,
     "audience": "website visitors last 30 days", "status": "paused",
     "notes": "Paused after CPA rose above target for three straight weeks."},
    {"id": "CMP-006", "name": "Customer Story Video", "channel": "video",
     "spend": 24000, "leads": 610, "conversions": 92, "revenue": 64400,
     "audience": "small business owners", "status": "completed",
     "notes": "Short customer-story clips cut for social and the website."},
    {"id": "CMP-007", "name": "Partner Co-Marketing", "channel": "email",
     "spend": 12000, "leads": 880, "conversions": 132, "revenue": 66000,
     "audience": "partner referral lists", "status": "active",
     "notes": "Joint newsletter sends with two integration partners."},
    {"id": "CMP-008", "name": "SEO Content Sprint", "channel": "organic",
     "spend": 15000, "leads": 1120, "conversions": 134, "revenue": 60300,
     "audience": "organic search visitors", "status": "active",
     "notes": "Ten guides targeting comparison and pricing-intent keywords."},
]

SEGMENTS = [
    {"id": "SEG-001", "name": "Mid-market ops leaders", "size": 18400,
     "criteria": "51-500 employees, operations or revenue-ops title, US",
     "crm_source": "CRM contacts synced from the sales database",
     "notes": "Highest email engagement; responds to workflow automation content."},
    {"id": "SEG-002", "name": "Enterprise marketing VPs", "size": 6200,
     "criteria": "1000+ employees, VP or above in marketing, named accounts",
     "crm_source": "CRM named-account list, refreshed weekly",
     "notes": "Small but high value; prefers peer stories and ROI evidence."},
    {"id": "SEG-003", "name": "Small business owners", "size": 42300,
     "criteria": "1-50 employees, owner or founder, any industry",
     "crm_source": "CRM plus website signup list",
     "notes": "Largest segment; price-sensitive; short decision cycles."},
    {"id": "SEG-004", "name": "High-intent searchers", "size": 9100,
     "criteria": "visited pricing page in the last 14 days",
     "crm_source": "CDP behavioural events joined to CRM contacts",
     "notes": "Built from CDP page-view events; refreshes daily."},
    {"id": "SEG-005", "name": "Marketing practitioners", "size": 27800,
     "criteria": "manager or specialist in marketing, engaged with content",
     "crm_source": "CDP engagement scores joined to CRM contacts",
     "notes": "Webinar and guide audience; strong top-of-funnel response."},
    {"id": "SEG-006", "name": "Partner referral lists", "size": 5400,
     "criteria": "referred by an integration partner, opted in",
     "crm_source": "Partner portal export loaded into the CRM",
     "notes": "Warmest cold audience; converts above the house average."},
]

CONTENT_ASSETS = [
    {"id": "AST-001", "title": "Marketing Automation Buyer's Guide", "type": "guide",
     "channel": "organic", "campaign_id": "CMP-008",
     "summary": "Comparison guide for marketing automation platforms, pricing and setup effort."},
    {"id": "AST-002", "title": "Spring Launch Announcement Email", "type": "email",
     "channel": "email", "campaign_id": "CMP-001",
     "summary": "Launch email announcing the new workflow builder and templates."},
    {"id": "AST-003", "title": "ROI Calculator Landing Page", "type": "landing page",
     "channel": "paid search", "campaign_id": "CMP-002",
     "summary": "Interactive calculator showing time saved by automating follow-up emails."},
    {"id": "AST-004", "title": "ABM Playbook for Enterprise VPs", "type": "guide",
     "channel": "paid social", "campaign_id": "CMP-003",
     "summary": "Account-based marketing playbook with targeting and measurement checklists."},
    {"id": "AST-005", "title": "Webinar: Automating Lead Follow-Up", "type": "webinar",
     "channel": "webinar", "campaign_id": "CMP-004",
     "summary": "Live walkthrough of automated lead follow-up sequences and reporting."},
    {"id": "AST-006", "title": "Customer Story: Northwind Traders", "type": "video",
     "channel": "video", "campaign_id": "CMP-006",
     "summary": "Customer story video on cutting manual reporting time with dashboards."},
    {"id": "AST-007", "title": "Retargeting Banner Set Q2", "type": "ad creative",
     "channel": "display", "campaign_id": "CMP-005",
     "summary": "Display banner set for visitors who viewed pricing but did not sign up."},
    {"id": "AST-008", "title": "Partner Newsletter Feature", "type": "email",
     "channel": "email", "campaign_id": "CMP-007",
     "summary": "Joint partner newsletter feature on the integration and shared customers."},
    {"id": "AST-009", "title": "Pricing Comparison Page", "type": "landing page",
     "channel": "organic", "campaign_id": "CMP-008",
     "summary": "Side-by-side pricing comparison page for evaluation-stage visitors."},
    {"id": "AST-010", "title": "Webinar Replay: Reporting Basics", "type": "webinar",
     "channel": "webinar", "campaign_id": "CMP-004",
     "summary": "On-demand replay of the reporting-basics session with templates."},
]

FIRST_NAMES = ["Ava", "Liam", "Maya", "Noah", "Zoe", "Ethan", "Ivy", "Owen",
               "Lena", "Caleb", "Nora", "Felix", "Ruby", "Hugo", "Tara",
               "Miles", "June", "Silas", "Wren", "Dante"]
LAST_NAMES = ["Chen", "Patel", "Garcia", "Kim", "Novak", "Singh", "Brooks",
              "Hayes", "Fischer", "Osei", "Larsen", "Costa", "Meyer",
              "Reyes", "Kaur", "Walsh", "Dubois", "Nakamura", "Petrov", "Ali"]
COMPANIES = ["Northwind Traders", "BlueRock Labs", "Harbor & Main",
             "Summit Analytics", "Copperfield Media", "Juniper Works",
             "Atlas Freight", "Beacon Retail Group"]


def generate_contacts(n: int = 200, seed: int = SEED) -> list[dict]:
    """Deterministic synthetic CRM-like contacts (seeded; invented names)."""
    rng = random.Random(seed)
    contacts = []
    for i in range(n):
        segment = rng.choice(SEGMENTS)
        contacts.append({
            "id": f"CON-{i + 1:04d}",
            "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            "company": rng.choice(COMPANIES),
            "segment_id": segment["id"],
            "email_opt_in": rng.random() < 0.8,
            "lifecycle_stage": rng.choice(
                ["subscriber", "lead", "marketing qualified lead", "customer"]),
        })
    return contacts


def campaign_text(campaign: dict) -> str:
    cpa = campaign["spend"] / campaign["conversions"] if campaign["conversions"] else 0
    roi = campaign["revenue"] / campaign["spend"] if campaign["spend"] else 0
    return (
        f"Campaign {campaign['id']} {campaign['name']}. Channel {campaign['channel']}. "
        f"Status {campaign['status']}. Audience {campaign['audience']}. "
        f"Spend ${campaign['spend']}. Leads {campaign['leads']}. "
        f"Conversions {campaign['conversions']}. Revenue ${campaign['revenue']}. "
        f"Cost per acquisition ${cpa:.2f}. Return on spend {roi:.2f}x. {campaign['notes']}"
    )


def segment_text(segment: dict) -> str:
    return (
        f"Segment {segment['id']} {segment['name']}. Size {segment['size']} contacts. "
        f"Criteria: {segment['criteria']}. Source: {segment['crm_source']}. {segment['notes']}"
    )


def asset_text(asset: dict) -> str:
    return (
        f"Content asset {asset['id']} {asset['title']}. Type {asset['type']}. "
        f"Channel {asset['channel']}. Campaign {asset['campaign_id']}. {asset['summary']}"
    )


def build_documents() -> list[dict]:
    """Every retrievable document: id, kind, and plain text."""
    docs = []
    for campaign in CAMPAIGNS:
        docs.append({"id": campaign["id"], "kind": "campaign",
                     "text": campaign_text(campaign)})
    for segment in SEGMENTS:
        docs.append({"id": segment["id"], "kind": "segment",
                     "text": segment_text(segment)})
    for asset in CONTENT_ASSETS:
        docs.append({"id": asset["id"], "kind": "content",
                     "text": asset_text(asset)})
    return docs
