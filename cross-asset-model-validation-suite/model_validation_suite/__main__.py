"""CLI entry point: ``python -m model_validation_suite``.

Runs every registered invariant over the scenario grids in the YAML config,
prints a pass/fail summary and writes ``summary.json`` + ``summary.csv``
(one row per check, ready for dashboard ingestion, e.g. Power BI).
Exit code is 1 when any check fails, 0 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .invariants import run_suite
from .report import summarise, write_csv, write_json
from .scenarios import expand_scenarios, load_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _PROJECT_ROOT / "configs" / "scenarios.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="model_validation_suite",
        description="Run cross-asset model validation invariants over YAML scenario grids.")
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG),
                        help="Path to the YAML scenario config (default: configs/scenarios.yaml)")
    parser.add_argument("--out-dir", default=str(_PROJECT_ROOT / "reports"),
                        help="Directory for summary.json / summary.csv (default: reports/)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    scenarios = expand_scenarios(config)
    results = run_suite(scenarios)
    summary = summarise(results, config_name=Path(args.config).name)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(results, out_dir / "summary.json", config_name=Path(args.config).name)
    write_csv(results, out_dir / "summary.csv")

    print("Cross-Asset Model Validation Suite")
    print(f"Config:    {args.config}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Checks:    {summary['total_checks']}  "
          f"Passed: {summary['passed']}  Failed: {summary['failed']}  "
          f"Pass rate: {summary['pass_rate']:.1%}")
    for asset, bucket in sorted(summary["by_asset_class"].items()):
        print(f"  {asset:<8} {bucket['passed']}/{bucket['checks']} passed")
    if summary["breaches"]:
        print("\nBreaches:")
        for b in summary["breaches"]:
            print(f"  FAIL {b['scenario_id']} :: {b['invariant']} -- {b['detail']}")
    print(f"\nWrote {out_dir / 'summary.json'}")
    print(f"Wrote {out_dir / 'summary.csv'}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
