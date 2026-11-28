# Marketing Mix, Attribution & Geo-Experiment Report

Seeded synthetic data (see README.md). All figures are demo results, not production marketing data.

## Marketing mix model

- Ridge alpha: 0.4832930238571752; R² (train): 0.993; holdout MAPE (last 12 weeks): 0.5%
- Total incremental sales over 104 weeks: 36705.2

| channel | coef per $1k | total spend $k | incremental sales | ROI | share |
|---|---|---|---|---|---|
| paid_search | 2.926 | 8294.5 | 16911.8 | 2.039 | 46.1% |
| paid_social | 1.74 | 6131.8 | 7692.6 | 1.255 | 21.0% |
| display | 1.134 | 4616.3 | 3888.6 | 0.842 | 10.6% |
| video | 1.18 | 5202.1 | 4424.6 | 0.851 | 12.1% |
| email | 2.579 | 1841.5 | 3787.6 | 2.057 | 10.3% |

Reallocation idea: move $461.6k (10% of spend) from display to email for an expected +560.9 incremental sales under the fitted model.

## Model monitoring (holdout weeks as new production data)

The 12 holdout weeks stand in for new production weeks: spend, seasonality and sales are checked for distribution shift against the training window, and holdout prediction error is checked against the holdout baseline. In production this runs on genuinely new weeks.
Verdict: WATCH — 5 distribution flag(s), new-week MAPE 0.5% vs holdout 0.5% (ratio 1.0x).
- spend_paid_search: 83.61 -> 50.2 (shift -1.35, p = 0.0) [FLAG]
- spend_paid_social: 59.15 -> 57.52 (shift -0.063, p = 0.8568) [ok]
- spend_display: 43.45 -> 51.56 (shift 0.559, p = 0.0456) [FLAG]
- spend_video: 48.12 -> 64.57 (shift 0.824, p = 0.0131) [FLAG]
- spend_email: 18.17 -> 14.13 (shift -0.631, p = 0.0254) [FLAG]
- seasonality: 10.13 -> -77.66 (shift -1.351, p = 0.0) [FLAG]
- sales: 1581.29 -> 1534.33 (shift -0.397, p = 0.279) [ok]

## Attribution (share of converted journeys)

| rule | paid_search | paid_social | display | video | email | organic_search |
|---|---|---|---|---|---|---|
| last_touch | 30.9% | 20.5% | 11.6% | 13.0% | 11.8% | 12.2% |
| first_touch | 31.0% | 20.9% | 11.9% | 12.3% | 11.2% | 12.7% |
| position_based | 30.7% | 20.8% | 11.8% | 12.6% | 11.7% | 12.4% |
| shapley | 38.5% | 16.8% | 4.3% | 12.3% | 14.3% | 13.8% |

Last-touch under-credits the assisting channels: Shapley gives email and organic search materially more credit than last-touch does, while paid search keeps a large share under both rules — the classic reason to pair MMM with attribution instead of trusting one view.

## Geo holdout experiment (paid social paused in treated DMAs)

- Treated DMAs: 10; control DMAs: 30
- Difference-in-differences: -47.4 signups/DMA/week, 95% CI (-58.0, -36.9), p = 0.0
- CUPED-adjusted: -52.1 signups/DMA/week, 95% CI (-97.8, -6.4), p = 0.0435
- True incremental lift in the simulation: 45.0 signups/DMA/week — both estimators recover it within noise.
- Recommendation: KEEP RUNNING paid social — the pause cost real incremental signups, so the channel is incremental and should stay on.

## Lead scoring (inbound leads, synthetic data)

- Leads scored: 2000; observed MQL rate: 38.6%; ROC-AUC 5-fold CV 0.755 (train 0.778, holdout 0.71).
- Calibration (predicted vs observed MQL rate by score band): (0.0458, 0.235]: pred 0.15 vs obs 0.16 (n=658); (0.235, 0.421]: pred 0.32 vs obs 0.33 (n=574); (0.421, 0.608]: pred 0.51 vs obs 0.50 (n=379); (0.608, 0.795]: pred 0.69 vs obs 0.66 (n=236); (0.795, 0.982]: pred 0.87 vs obs 0.84 (n=153).
- MQL tiers: cold 942, excluded 67, hot 425, nurture 112, warm 454. Competitor domains are excluded and leads below the 0.5 enrichment floor go to nurture, not to sales.
- Expected pipeline value of the scored leads: $34,448,142 (mean $17,224 per lead).
