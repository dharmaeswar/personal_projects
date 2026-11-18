"""Benchmark runner: parallel per-asset-class simulation, XVA ladder, CLI.

Asset classes are independent netting sets, so each one is simulated as a
separate work item. With ``parallel=True`` the work items run on a
``concurrent.futures.ProcessPoolExecutor`` (in the original workflow, joblib
was used the same way); ``--serial`` forces the in-process fallback. Every
asset class gets its own RNG stream derived from the master seed via
``SeedSequence.spawn``, so results are identical serial vs parallel.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List

import numpy as np

from .benchmark import run_benchmarks
from .config import (SimulationConfig, XVAConfig, config_to_dict,
                     default_asset_classes)
from .exposure import ExposureProfile, compute_exposure
from .portfolio import (default_portfolio, portfolio_values,
                        position_from_dict, position_to_dict)
from .simulation import simulate_gbm, time_grid
from .xva import xva_ladder, xva_totals


def _run_asset_class(payload: dict) -> dict:
    """Worker: simulate one asset class and build its exposure/XVA result."""
    asset = payload["asset"]
    sim = SimulationConfig(**payload["simulation"])
    xva_cfg = XVAConfig(**payload["xva"])
    positions = [position_from_dict(p) for p in payload["positions"]]
    times = time_grid(sim.horizon_years, sim.n_steps)
    rng = np.random.default_rng(payload["seed"])
    spots = simulate_gbm(asset["spot"], asset["volatility"],
                         sim.risk_free_rate, times, sim.n_paths, rng)
    values = portfolio_values(positions, spots, times, sim.risk_free_rate,
                              asset["volatility"])
    profile = compute_exposure(values, times, sim.risk_free_rate,
                               xva_cfg.pfe_quantile)
    totals = xva_totals(profile, xva_cfg)
    ladder = xva_ladder(profile, xva_cfg,
                        horizons=tuple(float(h) for h in
                                       range(1, int(sim.horizon_years) + 1)))
    return {
        "asset": asset["name"],
        "times": [float(t) for t in profile.times],
        "ee_profile": [float(v) for v in profile.ee],
        "pfe_profile": [float(v) for v in profile.pfe],
        "epe": float(profile.epe),
        **totals,
        "total_xva": float(totals["cva"] + totals["fva"] + totals["kva"]),
        "ladder": ladder,
    }


def run_benchmark_suite(sim_cfg: SimulationConfig | None = None,
                        xva_cfg: XVAConfig | None = None) -> dict:
    """Run the full benchmark: simulation, exposure, XVA, independent checks."""
    sim_cfg = sim_cfg or SimulationConfig()
    xva_cfg = xva_cfg or XVAConfig()
    assets = default_asset_classes()
    portfolio = default_portfolio(assets, sim_cfg.horizon_years)

    seed_sequence = np.random.SeedSequence(sim_cfg.seed)
    child_seeds = seed_sequence.spawn(len(assets))
    payloads = []
    for asset, child in zip(assets, child_seeds):
        payloads.append({
            "asset": {"name": asset.name, "spot": asset.spot,
                      "volatility": asset.volatility},
            "simulation": vars(sim_cfg),
            "xva": vars(xva_cfg),
            "positions": [position_to_dict(p) for p in portfolio[asset.name]],
            "seed": child,
        })

    if sim_cfg.parallel and len(payloads) > 1:
        with ProcessPoolExecutor(max_workers=len(payloads)) as pool:
            asset_results = list(pool.map(_run_asset_class, payloads))
    else:
        asset_results = [_run_asset_class(p) for p in payloads]

    totals = {
        key: float(sum(r[key] for r in asset_results))
        for key in ("cva", "fva", "kva", "total_xva")
    }
    totals["epe"] = float(sum(r["epe"] for r in asset_results))

    ladder_rows: List[Dict[str, float]] = []
    for result in asset_results:
        for row in result["ladder"]:
            ladder_rows.append({"asset": result["asset"], **row})
    horizon_keys = sorted({row["horizon_years"] for row in ladder_rows})
    for horizon in horizon_keys:
        rows = [r for r in ladder_rows if r["horizon_years"] == horizon]
        ladder_rows.append({
            "asset": "TOTAL",
            "horizon_years": horizon,
            "ee": float(sum(r["ee"] for r in rows)),
            "pfe": float(sum(r["pfe"] for r in rows)),
            "cum_cva": float(sum(r["cum_cva"] for r in rows)),
            "cum_fva": float(sum(r["cum_fva"] for r in rows)),
            "cum_kva": float(sum(r["cum_kva"] for r in rows)),
            "cum_total_xva": float(sum(r["cum_total_xva"] for r in rows)),
        })

    checks = run_benchmarks(assets, portfolio, sim_cfg, xva_cfg)

    return {
        "config": config_to_dict(sim_cfg, xva_cfg, assets),
        "assets": {r["asset"]: r for r in asset_results},
        "totals": totals,
        "ladder": ladder_rows,
        "benchmarks": [c.to_dict() for c in checks],
        "all_benchmarks_passed": bool(all(c.passed for c in checks)),
    }


def _print_report(results: dict) -> None:
    totals = results["totals"]
    print("=" * 78)
    print("Monte-Carlo XVA Benchmark Framework")
    print("=" * 78)
    print("\nXVA ladder (TOTAL portfolio, cumulative to horizon):")
    header = (f"{'Horizon':>8} {'EE':>12} {'PFE':>12} {'CVA':>12} "
              f"{'FVA':>12} {'KVA':>12} {'Total XVA':>12}")
    print(header)
    print("-" * len(header))
    for row in results["ladder"]:
        if row["asset"] != "TOTAL":
            continue
        print(f"{row['horizon_years']:>7.1f}y {row['ee']:>12,.2f} "
              f"{row['pfe']:>12,.2f} {row['cum_cva']:>12,.2f} "
              f"{row['cum_fva']:>12,.2f} {row['cum_kva']:>12,.2f} "
              f"{row['cum_total_xva']:>12,.2f}")
    print(f"\nTotals: CVA={totals['cva']:,.2f}  FVA={totals['fva']:,.2f}  "
          f"KVA={totals['kva']:,.2f}  Total XVA={totals['total_xva']:,.2f}")
    print("\nPer-asset-class XVA:")
    for name, r in results["assets"].items():
        print(f"  {name:<14} EPE={r['epe']:>12,.2f}  CVA={r['cva']:>10,.2f}  "
              f"FVA={r['fva']:>10,.2f}  KVA={r['kva']:>10,.2f}")
    print("\nIndependent benchmark checks (tolerance "
          f"{results['benchmarks'][0]['tolerance']:.1%}):")
    for check in results["benchmarks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"  [{status}] {check['name']:<28} {check['asset']:<14} "
              f"simulated={check['simulated']:>12,.4f}  "
              f"reference={check['reference']:>12,.4f}  "
              f"rel. error={check['relative_error']:.3%}")
    print(f"\nAll benchmarks passed: {results['all_benchmarks_passed']}")


def _write_outputs(results: dict, outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    json_path = os.path.join(outdir, "results.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    csv_path = os.path.join(outdir, "xva_ladder.csv")
    fieldnames = ["asset", "horizon_years", "ee", "pfe", "cum_cva",
                  "cum_fva", "cum_kva", "cum_total_xva"]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in results["ladder"]:
            writer.writerow({k: row[k] for k in fieldnames})
    print(f"\nWrote {json_path} and {csv_path}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Monte-Carlo XVA Benchmark Framework")
    parser.add_argument("--paths", type=int, default=10_000)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--horizon", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tolerance", type=float, default=0.012,
                        help="benchmark tolerance band (default 0.012 = 1.2%%)")
    parser.add_argument("--hazard-rate", type=float, default=0.02)
    parser.add_argument("--funding-spread", type=float, default=0.015)
    parser.add_argument("--serial", action="store_true",
                        help="disable parallel execution")
    parser.add_argument("--outdir", default="output")
    args = parser.parse_args(argv)

    sim_cfg = SimulationConfig(n_paths=args.paths, n_steps=args.steps,
                               horizon_years=args.horizon, seed=args.seed,
                               parallel=not args.serial)
    xva_cfg = XVAConfig(tolerance=args.tolerance,
                        hazard_rate=args.hazard_rate,
                        funding_spread=args.funding_spread)
    results = run_benchmark_suite(sim_cfg, xva_cfg)
    _print_report(results)
    _write_outputs(results, args.outdir)
    return 0 if results["all_benchmarks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
