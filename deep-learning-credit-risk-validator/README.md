# Deep-Learning Credit-Risk Validator

Independent validation of a deep-learning credit-card default model — the
kind of second-line validation a bank's model risk team runs before a
neural-network model is approved for use and while it stays in production.
Built for the Capital One Principal Associate, Data Scientist (Deep
Learning) role (Req R1006228, Plano, TX), and reused — with the
clustering segment analysis added — for the Capital One Principal
Associate, Data Scientist – GPN role (Req R1006407, Riverwoods IL /
McLean VA / Richmond VA), whose ideal candidate lists clustering
alongside classification, time series and deep learning.

**All data is synthetic and seeded.** No real borrower, bank, or customer
data is used, and nothing here is a claim about any real institution.

## The problem

A deep-learning model that scores credit-card applications can beat a
linear model on ranking — or it can just memorise the training book,
miscalibrate in the tails, and drift when the applicant mix shifts. A
model risk team cannot approve a model it has not challenged: it must
reproduce the developer's training code, build a challenger, backtest by
vintage, and watch the book drift after launch. This validator covers all
of it, in the shape of interagency model risk management guidance
(SR 26-2).

## What it validates

- **Candidate model** (`mlp.py`): a feed-forward neural network with two
  hidden layers (32, 16) and ReLU activations, written from scratch in
  NumPy — no deep-learning framework. Mini-batch gradient descent with
  momentum, L2 regularisation, and early stopping on validation loss.
- **Challenger model** (`challengers.py`): logistic regression, also from
  scratch in NumPy, fit and scored on the same splits.
- **Benchmark model**: base-rate predictor (overall default rate).
- **Numeric + textual data** (`data.py`): 6,000 synthetic applications
  with numeric fields (credit score, income, debt-to-income, revolving
  utilisation, history length, delinquencies, inquiries, balances) plus
  a free-text employment note encoded as keyword-count features.
- **Time-ordered splits** (`data.py`): train on 2024Q1–2025Q1, validate
  on 2025Q2, test on 2025Q3–2025Q4 — a model is never tested on
  applications originated before the ones it trained on.
- **Outcomes analysis** (`metrics.py`): ROC-AUC, KS, Gini, Brier score,
  confusion matrix at the operating threshold, decile capture, and
  calibration by predicted decile. All metrics are implemented from
  first principles (rank-based AUC, empirical CDFs for KS).
- **Backtesting** (`validation.py`): predicted vs realised default rate
  by origination quarter (vintage), breach when the ratio sits outside
  [0.80, 1.25].
- **Ongoing monitoring** (`validation.py`): Population Stability Index
  (PSI) for model scores and for each feature between the validation
  population and a later population.
- **Data integrity** (`validation.py`): missing values, duplicate rows,
  credit scores outside 300–850, utilisation outside [0, 1].
- **Sensitivity** (`validation.py`): permutation importance — the test
  AUC drop when one feature's values are shuffled.
- **Segmentation** (`segments.py`): k-means clustering (from scratch in
  NumPy, k-means++ seeding, empty-cluster re-seeding) groups the scored
  population into 4 risk segments; each segment is backtested on its
  own predicted vs realised default rate, flagged when the gap is
  wider than 0.10. A model can look calibrated overall while mispricing
  one segment, so the segment table is part of the report.
- **Implementation reproduction**: the MLP is re-fit from scratch with
  the same seed and its test scores compared within tolerance.
- **Findings and verdict** (`report.py`): severity-rated findings and a
  PASS / FAIL verdict, written to `validation_report.txt` / `.json`.

## Run it

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 run_validation.py   # prints the report, writes validation_report.txt/.json
PYTHONPATH=. python3 -m pytest -q        # test suite
```

## Results (seeded demo, 6,000 synthetic applications)

## Results (seeded demo, 6,000 synthetic applications)

- Candidate (MLP, 2 hidden layers, 40 epochs with early stopping):
  ROC-AUC **0.736**, KS **0.337**, Gini **0.473**, Brier 0.189;
  precision 0.639, recall 0.395, F1 0.489 at threshold 0.5; top scored
  decile captures **21.5%** of all defaults.
- Logistic challenger: ROC-AUC **0.750**, KS 0.373 — the challenger
  beats the neural network on this sample, and the report says so
  plainly instead of overselling the deep-learning model.
- Base-rate benchmark: ROC-AUC 0.500, as expected.
- Backtest: both test quarters inside [0.80, 1.25] (ratios 0.98, 1.02)
  — no breach.
- Segment backtest (k-means, k=4): all four segments calibrated, gaps
  0.009–0.031 — no segment flagged above 0.10.
- Monitoring: score PSI 0.018, worst feature PSI 0.038 — no drift flag.
- Top features by permutation importance: credit score (AUC drop
  0.160), delinquencies (0.032), history length (0.022), full-time
  employment text flag (0.012), debt-to-income (0.011).
- Implementation reproduces exactly on re-fit (max score diff 0.000000).
- Verdict: **FAIL — 1 High finding (F-01)**: the deep-learning
  candidate does not beat the simpler logistic challenger on test
  ROC-AUC. That is the finding a validator must surface before a
  neural-network model is approved for production use.

## Why this project is different from the others in the repo

`sb-credit-underwriting-validator` validates a small-business underwriting
model with logistic and gradient-boosting challengers; `fraud-model-validation`
validates a card-fraud scorer; `genai-model-validation-suite` validates a
generative-AI model with a rule-based stand-in; `ml-training-serving-platform`
trains a logistic model in plain Python. None of them trains a neural
network. This one builds, trains, and validates a **deep-learning**
candidate from scratch in NumPy — the model class the Capital One role
asks for — and challenges it against logistic and base-rate models with
vintage backtesting and drift monitoring.
