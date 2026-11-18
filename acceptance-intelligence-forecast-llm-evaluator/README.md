# Acceptance Intelligence — Forecast Backtesting + LLM Evaluation

A portfolio project for a Data Scientist role in payments acceptance
intelligence (time-series forecasting + NLP/LLM evaluation). It answers
two questions a model-validation team asks about an acceptance product:

1. **Which forecaster should we trust?** Walk-forward backtesting of
   three forecasters on a synthetic daily acceptance-rate series.
2. **Can we trust what the LLM says about the forecast?** An evaluation
   harness that scores LLM-generated analyst notes for grounding
   (every cited number must match a computed value), completeness, and
   runs a paired baseline-vs-tuned comparison with a bootstrap
   confidence interval and Bonferroni correction.

**All data is synthetic and seeded.** No real company, merchant, or
payment-network data is used, and nothing here is a claim about any
real institution.

## What it does

- `acceptance_eval/series.py` — seeded synthetic daily acceptance
  rates: upward trend, weekly seasonality (weekend dip), noise, and
  two holiday dips.
- `acceptance_eval/forecast.py` — seasonal-naive, Holt exponential
  smoothing, and a trend + day-of-week OLS forecaster (pure stdlib),
  plus MAE / RMSE / MAPE.
- `acceptance_eval/backtest.py` — walk-forward backtesting with
  expanding windows (6 folds, 7-day horizon).
- `acceptance_eval/llm_eval.py` — grounding scorer, completeness
  scorer, paired comparison (win rate, bootstrap 95% CI, exact
  sign-test p-value), Bonferroni correction.
- `run_evaluation.py` — runs the full pipeline and writes
  `evaluation_report.txt` and `evaluation_report.json`.

## Run it

```bash
pip install -r requirements.txt   # pytest only; the code itself is stdlib
python -m pytest tests -q
python run_evaluation.py
```

## Results (seed 7, 365 days, 6 folds x 7-day horizon)

Run `python run_evaluation.py` to regenerate; the report it writes
shows mean MAE/RMSE/MAPE per forecaster, which model wins, the
grounding scores of a grounded vs. an ungrounded LLM note, and the
paired tuned-vs-baseline comparison. On the seeded data the
trend-seasonal forecaster beats seasonal-naive on mean MAE, the
grounded note scores 1.00 grounding while the invented-number note
scores below 1.00 with its unsupported numbers listed, and the tuned
model wins all 10 paired prompts with the whole bootstrap 95% CI
above zero.

## Why this maps to acceptance intelligence

- Acceptance rates are a daily time series with weekly seasonality
  and holiday dips — the same shape as the series built here.
- Forecast quality is judged out-of-sample (walk-forward), not on
  training fit — the same discipline as model validation.
- LLM output is evaluated, not trusted: grounding checks catch
  invented metrics, and paired comparisons with CIs and
  multiple-comparison correction stop false "improvement" claims —
  the same statistical discipline used for model validation.
