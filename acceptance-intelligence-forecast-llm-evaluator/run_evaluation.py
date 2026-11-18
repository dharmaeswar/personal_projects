"""Run the acceptance-intelligence evaluation end to end.

1. Generate a seeded synthetic daily acceptance-rate series.
2. Walk-forward backtest three forecasters; pick the best by mean MAE.
3. Evaluate two sample LLM analyst notes (one grounded, one with an
   invented number) against the computed backtest metrics.
4. Run a paired baseline-vs-tuned comparison on synthetic per-prompt
   scores and apply a Bonferroni correction across metric families.
5. Write evaluation_report.txt and evaluation_report.json.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acceptance_eval import (  # noqa: E402
    generate_series,
    seasonal_naive,
    holt,
    trend_seasonal_forecast,
    walk_forward,
    score_grounding,
    score_completeness,
    paired_comparison,
    bonferroni,
)
from acceptance_eval.series import to_values  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED_TERMS = ["forecast", "mae", "seasonality", "drift", "recommendation"]


def main():
    series = generate_series(n_days=365, seed=7)
    values = to_values(series)

    models = {
        "seasonal_naive": lambda hist: seasonal_naive(hist, 7),
        "holt": lambda hist: holt(hist, 7),
        "trend_seasonal": lambda hist: trend_seasonal_forecast(hist, 7),
    }
    results = {}
    for name, fn in models.items():
        results[name] = walk_forward(values, fn, horizon=7, folds=6, step=7)
    best = min(results, key=lambda k: results[k]["mean_mae"])

    computed = {
        "mean_mae": round(results[best]["mean_mae"], 4),
        "mean_rmse": round(results[best]["mean_rmse"], 4),
        "mean_mape": round(results[best]["mean_mape"], 2),
    }
    good_note = (
        f"The {best} model forecasts acceptance with MAE {computed['mean_mae']} "
        f"and RMSE {computed['mean_rmse']}. Weekly seasonality and drift are "
        f"checked each fold. Recommendation: monitor the next holiday dip."
    )
    bad_note = (
        "The model forecasts acceptance with MAE 0.001 and RMSE 0.002. "
        "Weekly seasonality is fine. Recommendation: ship it now."
    )
    good = score_grounding(good_note, computed)
    bad = score_grounding(bad_note, computed)
    complete_good = score_completeness(good_note, REQUIRED_TERMS)
    complete_bad = score_completeness(bad_note, REQUIRED_TERMS)

    baseline = [0.72, 0.68, 0.75, 0.70, 0.74, 0.69, 0.73, 0.71, 0.76, 0.70]
    tuned = [0.81, 0.79, 0.83, 0.80, 0.82, 0.78, 0.84, 0.80, 0.85, 0.79]
    paired = paired_comparison(baseline, tuned)
    adjusted = bonferroni([paired["p_value"], 0.04, 0.30])

    report = {
        "series_days": len(values),
        "backtest": {k: {"mean_mae": round(v["mean_mae"], 4),
                          "mean_rmse": round(v["mean_rmse"], 4),
                          "mean_mape": round(v["mean_mape"], 2),
                          "worst_mae": round(v["worst_mae"], 4)}
                     for k, v in results.items()},
        "best_model": best,
        "computed": computed,
        "grounding_good_note": good,
        "grounding_bad_note": bad,
        "completeness_good_note": round(complete_good["completeness"], 2),
        "completeness_bad_note": round(complete_bad["completeness"], 2),
        "paired_baseline_vs_tuned": paired,
        "bonferroni_adjusted_p": [round(p, 4) for p in adjusted],
    }
    with open(os.path.join(HERE, "evaluation_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    lines = [
        "Acceptance Intelligence — Forecast + LLM Evaluation Report",
        f"Series: {len(values)} synthetic daily acceptance rates (seed 7)",
        "",
        "Walk-forward backtest (6 folds, 7-day horizon):",
    ]
    for name, v in results.items():
        lines.append(
            f"  {name}: mean MAE {v['mean_mae']:.4f}, "
            f"mean RMSE {v['mean_rmse']:.4f}, mean MAPE {v['mean_mape']:.2f}%"
        )
    lines += [
        f"Best model by mean MAE: {best}",
        "",
        f"Grounded note: grounding {good['grounding_rate']:.2f}, "
        f"completeness {complete_good['completeness']:.2f}",
        f"Ungrounded note: grounding {bad['grounding_rate']:.2f}, "
        f"unsupported numbers {bad['unsupported']}, "
        f"completeness {complete_bad['completeness']:.2f}",
        "",
        f"Paired tuned-vs-baseline: win rate {paired['win_rate']:.2f}, "
        f"mean diff {paired['mean_diff']:.3f}, "
        f"95% CI [{paired['ci_95'][0]:.3f}, {paired['ci_95'][1]:.3f}], "
        f"p {paired['p_value']:.4f}",
        f"Bonferroni-adjusted p-values: {report['bonferroni_adjusted_p']}",
    ]
    with open(os.path.join(HERE, "evaluation_report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return report


if __name__ == "__main__":
    main()
