# Air Load Planning — Weight & Balance, Auto Verification, Scale Log

A load-planning and weight-and-balance service for a cargo aircraft, in
the shape of the Amazon Air Safety Tech portfolio (SABLE load planning
and W&B, Auto Load Verification, Digital Scale Log, event-driven
messaging between systems).

Built for the Amazon — Software Development Engineer II, Air Safety &
Gateway Optimization (Job 10607522) application.

**Demo project. Synthetic data only. Not a real aircraft system.**
Nothing here contacts a real airline, and no production deployment,
customer use, or real flight history is claimed. All aircraft numbers
(empty weight, arms, compartment limits, CG envelope) are stated
planning assumptions for a generic narrow-body freighter, not a real
type certificate or load manual.

## What it does

- `airload/weight_balance.py` — weight-and-balance math: total weight,
  CG arm and % MAC from item weights and arms; checks MTOW, MZFW and
  the weight-dependent CG envelope, and lists every violation.
- `airload/load_plan.py` — load-plan builder: assigns cargo ULDs to
  FWD / AFT / BULK holds (each with its own capacity limit), adds fuel,
  and finalizes into a plan with a computed CG and envelope verdict.
- `airload/verification.py` — Auto Load Verification (ALV): rebuilds
  weight, CG and compartment totals from the raw items and compares
  them with the submitted plan figures within stated tolerances
  (50 lb, 0.5% MAC); any tampered total or envelope violation fails.
- `airload/scale_log.py` — Digital Scale Log: append-only scale
  readings reconciled against planned weights per item, with drift
  beyond tolerance (100 lb or 1%) reported as plain-language findings.
- `airload/messaging.py` — in-memory SNS/SQS-style bus: a Topic fans
  load-plan events out to subscribed Queues; failed deliveries retry
  up to a limit, then move to the dead-letter queue.
- `airload/report.py` — text and JSON load sheets.
- `airload/cli.py` — `plan` / `verify` / `scales` / `simulate`
  subcommands; `verify --tamper` corrupts the submitted total to prove
  ALV catches it.

## Skills used

Only skills Dharma has verified: Python, pytest, REST-style service
design, data validation, Linux. This project does **not** claim Java,
AWS Lambda/CDK/DynamoDB, SNS/SQS, or aviation certification in
production — the messaging bus is an in-memory model of the SNS/SQS
shape, and the W&B math uses stated demo assumptions.

## Run it

```bash
python run_demo.py
python -m airload.cli plan
python -m airload.cli verify
python -m airload.cli verify --tamper   # proves ALV catches a bad total
python -m airload.cli scales
python -m airload.cli simulate
```

## Tests

```bash
python -m pytest -q
```

40 pytest tests: weight-and-balance 8, load plan 7, verification 8,
messaging 7, scale log 5, CLI 5 (counts verified by the test run;
update this line if the suite changes).
