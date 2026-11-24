#!/usr/bin/env python3
"""Run the full inventory-demand pipeline: data, forecast, allocate, simulate, A/B test, report.

Usage: python run_analysis.py [--reps N] [--out DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from inventory_ds import ab_test, data_gen, forecast, report
from inventory_ds.allocate import allocation_metrics, greedy_allocate, lp_allocate
from inventory_ds.simulate import simulate, simulation_summary

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory-demand allocation pipeline")
    parser.add_argument("--reps", type=int, default=500, help="Monte Carlo replications")
    parser.add_argument("--out", type=Path, default=ROOT / "output", help="Output directory")
    args = parser.parse_args()

    history = data_gen.generate_demand_history()
    inventory = data_gen.generate_inventory()
    experiment = data_gen.generate_ab_experiment()
    (ROOT / "data").mkdir(exist_ok=True)
    history.to_csv(ROOT / "data" / "demand_history.csv", index=False)
    inventory.to_csv(ROOT / "data" / "inventory_snapshot.csv", index=False)
    experiment.to_csv(ROOT / "data" / "ab_experiment.csv", index=False)

    fc = forecast.forecast_all(history)
    greedy_metrics = allocation_metrics(greedy_allocate(fc, inventory), fc)
    lp_metrics = allocation_metrics(lp_allocate(fc, inventory), fc)
    sim = simulate(fc, inventory, history, n_reps=args.reps)
    sim_sum = simulation_summary(sim)
    ab = ab_test.analyse_ab(experiment)

    charts = report.make_charts(history, fc, sim_sum, ab, args.out)
    report.write_report(fc, greedy_metrics, lp_metrics, sim_sum, ab, charts,
                        args.out / "report.md")

    print(f"Forecast: mean HW sMAPE {fc['holt_winters_smape'].mean():.3f}, "
          f"mean Ridge sMAPE {fc['ridge_smape'].mean():.3f}")
    print(f"Greedy fill rate {greedy_metrics['fill_rate']:.1%}, "
          f"cost ${greedy_metrics['total_cost']:,.2f}")
    print(f"LP fill rate {lp_metrics['fill_rate']:.1%}, cost ${lp_metrics['total_cost']:,.2f}")
    print(f"A/B: fill-rate lift {ab['fill_rate_lift_pp']} pp (p={ab['fill_rate_p_value']}); "
          f"{ab['recommendation']}")
    print(f"Report written to {args.out / 'report.md'}")


if __name__ == "__main__":
    main()
