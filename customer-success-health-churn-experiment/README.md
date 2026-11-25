# Customer Success Health, Churn & Experimentation

End-to-end customer-success data science for a QuickBooks-style SMB platform:
a customer health score, churn and expansion propensity models, a next-best-action
ranker, KPI definitions, and causal evaluation of two investments — a
randomized onboarding intervention and a non-randomized coverage rollout.
Built for Intuit's Senior Data Scientist, Customer Success posting (Job 25135).

**Honest note:** all data is synthetic and seeded (see `customer_success/data.py`).
This is a demo built to show the methods, not production customer data and not
a claim of real Intuit experience. Both treatment effects are planted with a
known size so every estimate can be checked against the truth.

## What it does

1. **Health scoring** (`customer_success/health.py`) — one 0–100 score per
   customer from adoption (30%), engagement (25%), support load (20%), tenure
   (15%) and advocacy (10%), banded Healthy ≥ 70 / Watch 50–69 / At-Risk < 50.
   The score earns its keep: retention is 76% for Healthy, 54% for Watch and
   34% for At-Risk customers.
2. **Propensity models** (`customer_success/propensity.py`) — logistic
   regression from scratch (standard library only: standardization, gradient
   descent, L2) for churn and for expansion, judged on held-out customers:
   churn AUC 0.718, expansion AUC 0.711.
3. **Onboarding A/B test** (`customer_success/experiments.py`) — randomized
   guided-setup intervention: time-to-value falls 5.4 days (9.0 vs 14.4,
   p < 0.001) and retention rises 7.4 points (63.7% vs 56.3%, p = 0.0002).
   An SRM chi-square check passes (p = 0.25), and a CUPED adjustment with a
   single pooled theta correctly finds no effect on post-period usage
   (p = 0.66) — the intervention moves time-to-value, not usage.
4. **Coverage investment, causally** — the rollout went mostly to larger
   firms, so a naive treated-vs-control comparison is confounded. Two
   estimators that handle non-random assignment agree: difference-in-differences
   on usage gives +0.077 and a synthetic control (plan-segment donors, weights
   0.33/0.32/0.34, pre-period RMSE 0.009) gives +0.078, against the planted
   +0.08. The ship call is backed by the method, not by the raw gap.
5. **Next best action** (`customer_success/next_best_action.py`) — one ranked
   action per customer from health band + propensities: onboarding concierge
   for slow time-to-value, training for low adoption, coverage review for
   ticket-heavy Watch/At-Risk accounts, save plays for high churn propensity,
   expansion consults only for Healthy customers with headroom.
6. **KPIs as code** (`customer_success/kpis.py`) — one definition per metric
   (time-to-value, adoption, health mix, retention, expansion, tickets, NPS)
   computed from the same customers, so a leadership review reads the number
   the pipeline produced.

## Results (seeded run — `python run_analysis.py`)

- 2,400 synthetic SMB customers; median time-to-value 11 days; adoption 68.5%.
- Retention 59.9% overall; expansion 58.7% of retained customers.
- Health mix: 993 Healthy / 1,006 Watch / 401 At-Risk.
- Churn model held-out: AUC 0.718, log-loss 0.596, accuracy 0.675.
- Expansion model held-out: AUC 0.711, log-loss 0.590, accuracy 0.673.
- DiD +0.077 and synthetic control +0.078 vs planted coverage effect +0.08.

## Run it

```bash
python run_analysis.py        # full end-to-end run, prints every result above
python -m pytest tests/ -q    # 15 tests, all passing
```

Python 3.10+ standard library only; pytest is the only dev dependency.
