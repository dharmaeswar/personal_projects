# SB Credit Underwriting Validator

Independent validation of a small-business credit underwriting model —
the kind of second-line validation a bank's AI & Model Risk team runs
before a Square Loans-style model is approved for use and while it
stays in production. Built for the Block, Inc. Senior Model Risk
Analyst, AI & Model Risk role (Req R0007341).

**All data is synthetic and seeded.** No real borrower, bank, or
transaction data is used, and nothing here is a claim about any real
institution.

## The problem

A small-business underwriting model that approves the wrong borrowers
loses money; one that rejects the right ones loses the business. A
model risk team cannot approve a model it has not challenged: it must
reproduce the developer's code, test the input data, build a
challenger, backtest by vintage, and watch the book drift after
launch. This validator covers all of it, in the shape of interagency
model risk management guidance (SR 26-2).

## What it validates

- **Champion model** (`models.py`): the developer's logistic
  regression on revenue, years in business, cash-flow coverage,
  credit score, loan amount, and industry risk.
- **Challenger model**: an independent logistic regression adding
  interaction terms (revenue x coverage, score x years in business),
  benchmarked against the champion on the same validation sample.
- **Outcomes analysis** (`outcomes.py`): ROC-AUC, KS statistic, Gini,
  decile capture, calibration by predicted decile, and the confusion
  matrix at the operating threshold.
- **Backtesting** (`validation.py`): predicted vs realised default
  rate by origination quarter (vintage), with a breach flag when the
  ratio sits outside [0.80, 1.25].
- **Ongoing monitoring** (`validation.py`): Population Stability Index
  (PSI) and mean score drift between the validation population and a
  later production population.
- **Data integrity** (`validation.py`): duplicate keys, missing
  values, credit scores outside 300–850, non-positive revenue or
  loan amounts, implausible years in business.
- **Implementation reproduction** (`validation.py`): the developer
  model is re-fit independently from scratch and its outputs compared
  within tolerance.
- **Findings and rating** (`report.py`): severity-rated findings and
  an independent risk-rating recommendation, plus a full SR 26-2-style
  validation report.

## Run it

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 run_validation.py   # prints the report, writes validation_report.txt
PYTHONPATH=. python3 -m pytest -q        # 25 tests
```

## Results (seeded demo, 4,000 synthetic loans)

- Champion ROC-AUC **0.734**, KS **0.356**, Gini **0.468**; challenger
  0.735 — the interaction terms add almost nothing, which the report
  says plainly instead of overselling the challenger.
- Top scored decile captures **25.0%** of all defaults; bottom decile
  1.8%.
- At the operating threshold (t=0.5): precision 0.639, recall 0.091,
  F1 0.159 — the threshold trade-off the validator hands to the model
  owner.
- Backtest: all six origination quarters inside [0.80, 1.25]
  (ratios 0.95–1.20) — no breach.
- Monitoring: PSI 0.038 (below the 0.10 watch line); mean score drift
  10.6% — flagged Medium, re-check before the next quarterly review.
- Data: 2 credit scores outside 300–850 — flagged Medium.
- Developer code reproduces exactly (max abs diff 0.0000).
- Verdict: **PASS — approve for use**, recommended risk rating
  Medium (owner proposed Medium), with 3 Medium findings to track to
  closure.

## Why this project is different from the others in the repo

`expected-credit-loss-validation` validates loan-loss forecasting
math (IFRS 9 staging, ECL arithmetic); `compliance-model-risk-validator`
validates an AML transaction-monitoring alert model; `fraud-model-validation`
validates a card-fraud scorer; `genai-model-validation-suite` validates
generative-AI models. This one validates a **credit underwriting**
model end to end: conceptual soundness, developer-code reproduction,
vintage backtesting, challenger comparison, and SR 26-2-style
severity-rated findings for a small-business lending book — the core
work of the Block AI & Model Risk team.
