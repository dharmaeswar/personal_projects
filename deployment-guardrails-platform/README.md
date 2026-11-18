# Deployment Guardrails Platform

A portfolio project for a backend / continuous-delivery role
(Affirm's Developer Productivity team style). It models the platform
side of shipping software: instead of checking one release, it
checks the whole fleet. Services declare deployment templates, a
policy engine validates each template against shared guardrails, a
fleet dashboard scores every service's safety, every decision lands
in an audit log, and an on-call helper routes alerts and builds
keep-the-lights-on checklists.

**All data is synthetic and local.** No real services, deployments,
or production traffic are involved, and nothing here is a claim about
any real company's systems.

## What it does

- **Deployment-template registry**
  (`deployment_guardrails/templates.py`) — services declare how
  they want to deploy: health checks, CPU/memory limits, canary
  stages, rollback plan, on-call owner and backup, and the planned
  deploy time. Templates load from `services.json` and tolerate
  missing fields.
- **Policy engine** (`deployment_guardrails/policies.py`) — six
  guardrails run over each template: readiness + liveness health
  checks present, CPU/memory limits declared and inside the
  platform caps (4 cores, 8192 MB), rollback plan naming a previous
  version with steps and automated rollback enabled, canary stages
  starting at 5% or less, increasing strictly, and ending at 100%,
  a primary on-call owner plus a different backup owner, and no
  deploy inside a change-freeze window (weekends, or 22:00-06:00
  UTC). Any failed guardrail rejects the template and every
  violation is listed.
- **Fleet rollout dashboard** (`deployment_guardrails/fleet.py`) —
  per-service rollout status (deployable / at risk / blocked) and a
  0-100 safety score from guardrail pass rate (40 pts), SLO health
  (30 pts), remaining error budget (20 pts), and open incidents
  (10 pts). SLO breaches and exhausted error budgets are flagged.
- **Audit log** (`deployment_guardrails/audit.py`) — every
  deployment decision is recorded in SQLite
  (`fleet_data/guardrails.db`): who asked, what was decided, when,
  and which guardrails failed. Queryable by service and by date,
  with a rejection count.
- **On-call helper** (`deployment_guardrails/oncall.py`) — alert
  routing rules map severity to who gets paged, the channel, and
  the escalation delay (sev1 pages the owner + incident commander
  and escalates in 5 minutes; sev4 becomes a ticket). The
  keep-the-lights-on checklist generator fills in a service's own
  availability, error budget, incidents, and last policy decision.
- **Fleet report** (`deployment_guardrails/report.py`) — one text
  report for the whole fleet, with violations per service and the
  checklist for the riskiest service.

## Results of a run

`python3 run_platform.py` evaluates four demo services from
`services.json`:

```
Services checked: 4  Deployable: 3  Blocked: 1  Guardrail violations: 6
Average safety score: 81.2/100  Audit entries today: 4  Total rejections on record: 1
  checkout-api v2.4.0: deployable (safety 100/100, 6/6 guardrails)
  search-api v3.1.0: deployable (safety 95/100, 6/6 guardrails)
  billing-worker v1.9.2: blocked (safety 30/100, 0/6 guardrails)
  payments-api v4.2.1: deployable (safety 100/100, 6/6 guardrails)
```

- **checkout-api v2.4.0** — 6/6 guardrails, SLO met (99.950% vs
  99.900%), 62% error budget left, no incidents: safety 100/100.
- **search-api v3.1.0** — 6/6 guardrails, but SLO breached
  (99.820% vs 99.900%) and 1 open incident: safety 95/100.
- **billing-worker v1.9.2** — 0/6 guardrails: no readiness/liveness
  checks, 8 CPU cores and 16384 MB over the platform caps, manual
  rollback only, canary starting at 25%, no backup on-call owner,
  and a Saturday 23:00 UTC deploy inside the freeze window. SLO
  breached (99.310% vs 99.500%), error budget exhausted, 2 open
  incidents: safety 30/100, blocked.
- **payments-api v4.2.1** — 6/6 guardrails, SLO met, 45% error
  budget left: safety 100/100.

The report lands in `fleet_reports/fleet-report.txt` and the audit
log in `fleet_data/guardrails.db` (4 decisions recorded, 1 rejection).

## How to run

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python3 run_platform.py           # demo: guardrails, fleet scores, audit log, report
python3 -m pytest -q              # 18 tests
```

## Layout

```
deployment_guardrails/
  templates.py   deployment-template registry (declared configs)
  policies.py    policy engine: six platform guardrails
  fleet.py       fleet dashboard: status, safety score, SLO / budget
  audit.py       SQLite audit log of deployment decisions
  oncall.py      alert routing + keep-the-lights-on checklists
  report.py      fleet text report generator
run_platform.py  runner: registry -> guardrails -> fleet -> audit -> report
services.json    demo fleet definitions (templates + reliability numbers)
tests/           18 pytest tests
```

## Honest limits

- The guardrails validate declared configs; they do not talk to a
  real deploy system, and the demo services are hand-written, not
  observed fleets.
- The safety score is a simple weighted model (40/30/20/10), not a
  calibrated reliability metric — it ranks services, it does not
  prove one is safe.
- The audit log is local SQLite, not a shared, tamper-proof record;
  it records what this platform ran, not what any team shipped.
- Alert routing is a static severity table, not a live paging
  integration; no alert is actually sent anywhere.
- No Kubernetes, AWS, or MySQL is used or claimed here; the
  platform runs entirely on local Python and SQLite.
