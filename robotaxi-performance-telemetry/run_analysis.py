"""Run the robotaxi performance analysis and write a readiness report.

Usage: python run_analysis.py [--trips N] [--seed S] [--out report.md]
"""
from __future__ import annotations

import argparse
import json

from robotaxi_telemetry.data import generate_trips, to_rows
from robotaxi_telemetry.metrics import kpi_summary, kpi_by_release, kpi_by_road
from robotaxi_telemetry.stats import poisson_rate_ci_per_1k, compare_rates


def analyse(n_trips: int = 1200, seed: int = 42) -> dict:
    rows = to_rows(generate_trips(n_trips, seed))
    overall = kpi_summary(rows)
    by_release = kpi_by_release(rows)
    by_road = kpi_by_road(rows)
    total_interventions = sum(r["interventions_total"] for r in rows)
    total_miles = sum(r["miles"] for r in rows)
    lo, hi = poisson_rate_ci_per_1k(total_interventions, total_miles)
    overall["interventions_per_1k_miles_ci95"] = [round(lo, 3), round(hi, 3)]
    comparisons = {}
    releases = sorted(by_release)
    for a, b in zip(releases, releases[1:]):
        ra = [r for r in rows if r["release"] == a]
        rb = [r for r in rows if r["release"] == b]
        comparisons[f"{a}_vs_{b}"] = compare_rates(
            sum(r["interventions_total"] for r in ra),
            sum(r["miles"] for r in ra),
            sum(r["interventions_total"] for r in rb),
            sum(r["miles"] for r in rb),
        )
    return {
        "overall": overall,
        "by_release": by_release,
        "by_road": by_road,
        "release_comparisons": comparisons,
    }


def render_markdown(result: dict) -> str:
    lines = ["# Robotaxi Performance & Capability — Readiness Report (synthetic data)",
             "",
             "## Overall KPIs",
             ""]
    for k, v in result["overall"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## KPIs by software release", ""]
    for rel, kpis in result["by_release"].items():
        lines.append(
            f"- {rel}: {kpis['trips']} trips, {kpis['miles']} miles, "
            f"{kpis['interventions_per_1k_miles']} interventions/1k miles, "
            f"mission completion {kpis['mission_completion_rate']}, "
            f"mean recovery {kpis['mean_recovery_min']} min"
        )
    lines += ["", "## KPIs by road type", ""]
    for road, kpis in result["by_road"].items():
        lines.append(
            f"- {road}: {kpis['interventions_per_1k_miles']} interventions/1k miles, "
            f"mission completion {kpis['mission_completion_rate']}"
        )
    lines += ["", "## Release-over-release rate comparison (Poisson, two-sided)", ""]
    for name, comp in result["release_comparisons"].items():
        verdict = (
            "SIGNIFICANT change" if comp["significant_95"] else "not significant — treat as noise"
        )
        lines.append(
            f"- {name}: rate ratio {comp['rate_ratio']}, p-value {comp['p_value']} — {verdict}"
        )
    lines += ["",
              "## Readiness read",
              "",
              "Later releases show lower intervention rates and higher mission completion in this synthetic sample; "
              "the Poisson comparisons say which of those moves clear the 95% bar and which are noise. "
              "Safety-critical interventions are the rarest type and carry the widest relative uncertainty, "
              "so they need the most miles before a release claim is trusted."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trips", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="report.md")
    args = parser.parse_args()
    result = analyse(args.trips, args.seed)
    with open(args.out, "w") as fh:
        fh.write(render_markdown(result))
    with open("report.json", "w") as fh:
        json.dump(result, fh, indent=2)
    print(render_markdown(result))


if __name__ == "__main__":
    main()
