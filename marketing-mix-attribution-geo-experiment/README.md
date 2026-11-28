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
4. **Model monitoring** (`mmm_geo/monitoring.py`, added Nov 27, 2026) — the
   production half of the work: new weeks are checked for distribution
   shift (standardised mean shift + Welch's t-test per spend channel,
   seasonality and sales) and for prediction drift (new-week MAPE vs the
   holdout baseline). Verdict is OK / WATCH / RETRAIN. Features are built
   on the full series so adstock carryover is not silently reset.
5. **Lead scoring** (`mmm_geo/lead_scoring.py`, added Nov 28, 2026) — the
   GTM production-model half: a logistic-regression scorer over 2,000
   synthetic inbound leads (channel, engagement signals, trial/demo,
   enrichment completeness, company size), a calibration check of
   predicted vs observed MQL rate by score band, MQL tier bands (hot /
   warm / cold) with routing rules — competitor domains excluded, leads
   below the enrichment floor sent to nurture, demo requests fast-tracked
   to hot — and expected lead value (score × deal size by size band).

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
- Model monitoring (holdout weeks as new production weeks): verdict WATCH —
  new-week MAPE 0.5%, identical to the holdout baseline (ratio 1.0x), so
  prediction error has not drifted; but 5 of 7 series are flagged for
  distribution shift, driven by seasonality (10.13 → −77.66) and the
  spend mix moving with it (paid search 83.61 → 50.2, video 48.12 → 64.57).
  That is the seasonal pattern in the generator, not a broken model — the
  honest read is to watch the next weeks and retrain if the error follows.
- Lead scoring: 2,000 synthetic inbound leads, observed MQL rate 38.6%;
  logistic scorer ROC-AUC 0.755 (5-fold CV). Calibration is close in every
  band (e.g. top band: predicted 0.87 vs observed 0.84, n=153). MQL tiers:
  hot 425, warm 454, cold 942, nurture 112 (enrichment below the floor),
  excluded 67 (competitor domains). Expected pipeline value of the scored
  leads: $34,448,142 (mean $17,224 per lead).

## How to run

```bash
pip install -r requirements.txt
python run_analysis.py   # writes output/report.md and two charts
python -m pytest -q      # 31 tests
```

## Layout

- `mmm_geo/data_gen.py` — seeded synthetic data + documented ground truth
- `mmm_geo/mmm.py` — adstock, Hill saturation, Ridge MMM, reallocation
- `mmm_geo/attribution.py` — last/first/position-based + exact Shapley
- `mmm_geo/geo_experiment.py` — DiD + CUPED geo holdout analysis
- `mmm_geo/monitoring.py` — distribution-shift + prediction-drift monitoring, OK / WATCH / RETRAIN
- `mmm_geo/report.py` — runs everything, writes `output/report.md`
- `data/` — generated CSVs (weekly mix, geo panel, journeys)
- `output/` — `report.md`, `mmm_contributions.png`, `geo_holdout.png`
- `tests/test_mmm_geo.py` — 13 tests, all passing
- `tests/test_monitoring.py` — 9 tests, all passing

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
