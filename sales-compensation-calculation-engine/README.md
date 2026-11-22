# Sales Compensation Calculation Engine

A local, end-to-end sales compensation engine built in Python (standard
library only) — a portfolio project matching Block's **Sales Compensation
Systems & Data Engineer** role: the technical foundation of sales
compensation operations — data pipelines, integrations, data models,
calculation logic, testing, audit trails and reconciliation.

**All data is synthetic and seeded in code.** No real company or customer
data appears anywhere in this project, and nothing here was used in
production or by any real company.

## What it does

| Module | Block JD item |
|---|---|
| `comp_engine/plans.py` | **Comp plan versioning** — register plan versions, resolve the version effective on a deal's close date, reject overlapping versions and invalid tiers; plan changes never rewrite history |
| `comp_engine/crediting.py` | **Crediting rules** — owner credit, split crediting across reps, refunded/churned/pending deals credit $0; quota attainment per rep |
| `comp_engine/calculation.py` | **Calculation logic** — tiered rates by attainment, accelerators above threshold, per-deal caps, Decimal money rounded to cents |
| `comp_engine/adjustments.py` | **Adjustments** — clawbacks inside the clawback window, approver-gated manual adjustments, SPIFF bonuses |
| `comp_engine/payments.py` | **Payment workflow** — per-rep payout schedule, holdback withheld until the clawback window passes, scheduled → approved → paid, held reps |
| `comp_engine/audit.py` | **Audit trail** — append-only, hash-chained event log; any tampering breaks the chain and is detectable |
| `comp_engine/reconciliation.py` | **Reconciliation** — three-way check of CRM deals vs calculated commissions vs payroll payments, with named findings |
| `comp_engine/models.py` | **Data model** — dataclasses plus SQL DDL for the warehouse tables (`comp_reps`, `comp_deals`, `comp_plans`, `comp_commissions`, `comp_audit_log`) |
| `run_comp.py` | End-to-end demo: seeds 3 reps, 5 deals and 2 plan versions, runs the full pipeline and writes `comp_report.txt` / `comp_report.json` |

## How to run

```bash
pip install -r requirements.txt   # pytest only
python run_comp.py                # demo: writes comp_report.txt + comp_report.json
python -m pytest -q               # tests
```

Requires Python 3.12. The app code uses only the standard library, so it
runs anywhere with system Python.

## Demo results (real run)

Seeded run: **3 reps, 5 deals, 2 plan versions** (v1 at 10% top tier,
v2 at 12% from Nov 1 — November deals calculate under v2).

- **Crediting:** split deal D1002 credits 80% to its owner and 20% to the
  split partner; refunded deal D1004 credits $0.
- **Calculation:** attainment drives the tier — 90.5% and 57.2% attainment
  pay 8%, 25% attainment pays 6%.
- **Adjustments:** the refunded deal claws back $7,200 (51 days after
  close, inside the 90-day window); a $1,500 new-logo SPIFF is added.
- **Payments:** 3 payments, total net commission **$84,100.00**, total
  payable after the 10% holdback **$75,690.00**.
- **Audit:** 15 events, hash chain valid.
- **Reconciliation:** 0 findings — CRM, calculated and paid all agree.
