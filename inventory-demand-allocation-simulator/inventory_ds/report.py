"""Charts and the markdown summary report for the full pipeline run."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def make_charts(history: pd.DataFrame, forecast: pd.DataFrame,
                sim_summary: pd.DataFrame, ab: dict, out_dir: Path) -> list[str]:
    """Write three charts; return their filenames."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []

    # 1. Demand history + next-4-week forecast for one illustrative series.
    series = history[(history["style"] == "style_A") & (history["region"] == "east")]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.plot(series["week"], series["demand"], label="Observed weekly demand")
    last_week = int(series["week"].max())
    fc = forecast[(forecast["style"] == "style_A") & (forecast["region"] == "east")]
    total_4w = float(fc["forecast_total_4w"].iloc[0])
    ax.plot([last_week, last_week + 4], [series["demand"].iloc[-1], total_4w / 4],
            "o--", label=f"Forecast (best model: {fc['best_model'].iloc[0]})")
    ax.set_xlabel("Week")
    ax.set_ylabel("Units demanded")
    ax.set_title("Style A — East region: demand history and forecast")
    ax.legend()
    fig.tight_layout()
    p = out_dir / "demand_forecast.png"
    fig.savefig(p)
    plt.close(fig)
    files.append(p.name)

    # 2. Fill-rate distribution across Monte Carlo replications (both policies).
    fig, ax = plt.subplots(figsize=(8, 3.5))
    for policy, row in sim_summary.iterrows():
        ax.bar(row["policy"], row["mean_fill_rate"], yerr=[[row["mean_fill_rate"] - row["p5_fill_rate"]],
               [row["p95_fill_rate"] - row["mean_fill_rate"]]], capsize=6)
    ax.set_ylim(0.8, 1.0)
    ax.set_ylabel("Fill rate (5th–95th percentile band)")
    ax.set_title("Monte Carlo fill rate by sourcing policy (500 replications)")
    fig.tight_layout()
    p = out_dir / "fill_rate_by_policy.png"
    fig.savefig(p)
    plt.close(fig)
    files.append(p.name)

    # 3. A/B test: fill-rate lift with its 95% CI.
    lo, hi = ab["fill_rate_ci_95_pp"]
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.errorbar([ab["fill_rate_lift_pp"]], [0], xerr=[[ab["fill_rate_lift_pp"] - lo],
                [hi - ab["fill_rate_lift_pp"]]], fmt="o", capsize=6)
    ax.axvline(0, color="grey", linestyle="--")
    ax.set_yticks([])
    ax.set_xlabel("Fill-rate lift, treatment − control (percentage points, 95% CI)")
    ax.set_title(f"A/B test: fill-rate lift {ab['fill_rate_lift_pp']} pp (p = {ab['fill_rate_p_value']:.2g})")
    fig.tight_layout()
    p = out_dir / "ab_fill_rate_lift.png"
    fig.savefig(p)
    plt.close(fig)
    files.append(p.name)
    return files


def write_report(forecast: pd.DataFrame, greedy: dict, lp: dict,
                 sim_summary: pd.DataFrame, ab: dict, chart_files: list[str],
                 out_path: Path) -> None:
    """Write the markdown summary report."""
    lines = [
        "# Inventory–Demand Allocation — run report",
        "",
        "Synthetic data only. Seeded run; re-run `run_analysis.py` to reproduce.",
        "",
        "## Forecast (next 4 weeks, best model per series by holdout sMAPE)",
        "",
        forecast.to_markdown(index=False),
        "",
        f"Mean Holt-Winters holdout sMAPE: {forecast['holt_winters_smape'].mean():.3f}. "
        f"Mean Ridge holdout sMAPE: {forecast['ridge_smape'].mean():.3f}.",
        "",
        "## Allocation — week 1 (deterministic forecast)",
        "",
        f"- Greedy (nearest-FC first): fill rate {greedy['fill_rate']:.1%}, "
        f"total cost ${greedy['total_cost']:,.2f}, cost per filled unit ${greedy['cost_per_filled_unit']:.2f}.",
        f"- LP (cost-optimized): fill rate {lp['fill_rate']:.1%}, "
        f"total cost ${lp['total_cost']:,.2f}, cost per filled unit ${lp['cost_per_filled_unit']:.2f}.",
        "",
        "## Monte Carlo simulation (500 replications)",
        "",
        sim_summary.to_markdown(index=False),
        "",
        "## A/B test — cost-optimized sourcing vs nearest-FC",
        "",
        f"- Fill rate: control {ab['control_fill_rate']:.1%} vs treatment {ab['treatment_fill_rate']:.1%} "
        f"(lift {ab['fill_rate_lift_pp']} pp, 95% CI {ab['fill_rate_ci_95_pp']}, "
        f"p = {ab['fill_rate_p_value']:.2g}).",
        f"- Cost per order: control ${ab['control_mean_cost']:.2f} vs treatment "
        f"${ab['treatment_mean_cost']:.2f} (diff ${ab['cost_diff_per_order']:.2f}, "
        f"95% CI {ab['cost_ci_95']}, p = {ab['cost_p_value']:.2g}).",
        f"- Recommendation: **{ab['recommendation']}**.",
        "",
        "## Charts",
        "",
    ]
    lines += [f"- `{name}`" for name in chart_files]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
