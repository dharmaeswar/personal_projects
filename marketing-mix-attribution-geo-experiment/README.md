# Marketing Mix, Attribution & Geo-Experiment

End-to-end measurement of marketing effectiveness for a B2B SaaS business:
a marketing mix model (MMM), multi-touch attribution, and a geo holdout
experiment — the three methods in Figma's Data Scientist, Marketing posting.

**Honest note:** all data is synthetic and seeded (see `mmm_geo/data_gen.py`).
This is a demo built to show the methods, not production marketing data and
not a claim of real marketing experience. Ground-truth parameters are written
into the generator so every estimate can be checked against a known answer.

## What it does

1. **Marketing mix model** (`mmm_geo/mmm.py`) — 104 weeks of spend across
   paid search, paid social, display, video and email. Each channel's spend
   goes through geometric adstock (carryover, θ = 0.5) and Hill saturation,
   then a standardised Ridge regression on sales with seasonality, holiday
   and promo controls. The last 12 weeks are held out for validation.
   Output: per-channel coefficients, incremental sales, ROI, share of
   incremental sales, and a budget-reallocation idea.
2. **Multi-touch attribution** (`mmm_geo/attribution.py`) — 20,000 synthetic
   user journeys with independent per-channel touch inclusion. Four rules on
   the same journeys: last-touch, first-touch, position-based (40/20/40)
   and exact Shapley values from simulated coalition conversion rates.
3. **Geo holdout experiment** (`mmm_geo/geo_experiment.py`) — paid social is
   paused in 10 treated DMAs for 8 weeks against 30 control DMAs.
   Difference-in-differences plus a CUPED-adjusted estimate, Welch's t-test,
   95% confidence intervals, and a keep-running / inconclusive call.

## Results (seeded run — `python run_analysis.py`)

- MMM: R² (train) 0.993; holdout MAPE 0.5% (last 12 weeks). Total
  incremental sales over 104 weeks: 36,705. Fitted coefficients recover the
  known truth closely (paid search 2.93 vs true 2.6; email 2.58 vs true 3.1;
  paid social 1.74 vs true 1.9; video 1.18 vs true 1.4; display 1.13 vs
  true 0.9).
- ROI: email 2.06 and paid search 2.04 are the most efficient; display 0.84
  is the least. Moving 10% of display spend ($461.6k) to email is expected
  to add ~561 incremental sales under the fitted model.
- Attribution: last-touch gives paid search 30.9%; Shapley gives it 38.5%
  and credits the assisting channels more (email 14.3% vs 11.8% last-touch;
  organic search 13.8% vs 12.2%). Display is small under every rule
  (Shapley 4.3%) — consistent with the MMM, where it has the lowest ROI.
- Geo holdout: pausing paid social cost 47.4 signups/DMA/week (DiD, 95% CI
  −58.0 to −36.9, p < 0.0001); CUPED-adjusted −52.1 (95% CI −97.8 to −6.4,
  p = 0.044). True lift in the simulation is 45.0 — both estimators recover
  it. Recommendation: KEEP RUNNING paid social; the pause cost real
  incremental signups.

## How to run

```bash
pip install -r requirements.txt
python run_analysis.py   # writes output/report.md and two charts
python -m pytest -q      # 13 tests
```

## Layout

- `mmm_geo/data_gen.py` — seeded synthetic data + documented ground truth
- `mmm_geo/mmm.py` — adstock, Hill saturation, Ridge MMM, reallocation
- `mmm_geo/attribution.py` — last/first/position-based + exact Shapley
- `mmm_geo/geo_experiment.py` — DiD + CUPED geo holdout analysis
- `mmm_geo/report.py` — runs everything, writes `output/report.md`
- `data/` — generated CSVs (weekly mix, geo panel, journeys)
- `output/` — `report.md`, `mmm_contributions.png`, `geo_holdout.png`
- `tests/test_mmm_geo.py` — 13 tests, all passing

## Methods notes

- Features are standardised before Ridge: raw features live on very
  different scales, and unscaled Ridge shrinks them unevenly and can flip
  small-channel coefficients (caught by the tests during development).
- Attribution journeys use independent per-channel inclusion, not a fixed
  touch count, so a weak channel cannot displace a strong one and Shapley
  values stay non-negative.
- The CUPED interval is wider than the DiD interval here because the
  pre-period DMA means are noisy predictors; both are reported so the
  uncertainty is visible instead of hidden.
