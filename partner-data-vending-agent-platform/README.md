# Partner Data Vending & Agent Skills Platform

A portfolio project for a Software Engineer II role on an ads-partner
technology team (Amazon Ads Partner Tech style). It models the three pillars
of that team's mission with synthetic data: agent skills and knowledge
bases, trusted partner-data vending, and the platform that launches and
operates ML models.

**All data is synthetic and local.** No real partner, campaign, or model
data is used, and nothing here is a claim about any real company's systems.

## What it does

- **Agent skills** (`partner_platform/skills.py`) — skills declare inputs,
  required scopes, and a risk level. Low-risk skills auto-approve;
  medium- and high-risk skills need an explicit human approval, and a
  missing approval is recorded as a denial. Every invocation lands in an
  audit log.
- **Knowledge base** (`partner_platform/knowledge.py`) — partner documents
  are chunked into citable passages and indexed by keyword. A question
  returns the best-matching passages with citations; stale passages
  (past their freshness date) are flagged, and an answer backed only by
  stale passages is refused.
- **Trusted data vending** (`partner_platform/vending.py`) — data products
  declare required scopes and sensitive columns. A token must carry every
  required scope; sensitive columns are masked unless the token also holds
  `sensitive:read`; expired tokens vend nothing. Every access, granted or
  denied, is written to an append-only audit log.
- **ML model platform** (`partner_platform/models.py`) — a model version
  launches only when its checklist passes: green tests, recorded eval
  metrics, a rollback plan with version and steps, distinct primary and
  backup on-call owners, and a deploy window. Live models report latency
  and error rate against SLOs (500 ms, 5%), and a broken model rolls back
  to its previous version.
- **Agent orchestrator** (`partner_platform/agent.py`) — runs a partner
  request end to end: pick the skill, retrieve grounding knowledge, vend
  the trusted data the skill needs, check the live model — stopping at
  the first denial instead of producing a silent partial success.

## Run it

```bash
python run_platform.py
```

Runs one partner request (`campaign_insights` for campaign `cmp-101`)
through all four stages and prints the outcome as JSON.

## Tests

```bash
python -m pytest tests/ -q
```

24 tests: skill validation and approval gates, knowledge retrieval and
staleness, vending scope/masking/expiry denials, model launch checklist,
SLO health checks and rollback, and the agent's end-to-end happy path plus
its two denial paths.
