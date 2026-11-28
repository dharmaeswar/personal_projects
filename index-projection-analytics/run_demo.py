"""Seeded demo for Index Projection Analytics.

Builds the synthetic 8-name universe, applies a split, a dividend and a
spin-off, projects a rebalance with a new candidate, runs three return
scenarios, and compares a seeded index return series with a benchmark.
"""

from index_projection import (
    IndexUniverse,
    apply_split,
    apply_cash_dividend,
    apply_spinoff,
    project_rebalance,
    project_level,
    excess_returns,
    tracking_error,
    information_ratio,
)
from index_projection.demo_data import (
    build_demo_universe,
    DEMO_CANDIDATE,
    DEMO_SCENARIOS,
)


def main():
    universe = build_demo_universe()
    print(f"Base index level: {universe.level():.2f}")
    print("Weights:", {t: round(w, 4) for t, w in universe.weights().items()})

    print(f"After 2-for-1 split of AAA: level {apply_split(universe, 'AAA', 2):.2f}")
    print(
        f"After $1.50 BBB dividend: level "
        f"{apply_cash_dividend(universe, 'BBB', 1.50):.2f}"
    )
    print(
        f"After CCC spin-off ($12/share): level "
        f"{apply_spinoff(universe, 'CCC', 12.0, 'CCCS'):.2f}"
    )

    proj = project_rebalance(universe, [DEMO_CANDIDATE], target_count=8)
    print(f"Projected rebalance: additions {proj.additions}, deletions {proj.deletions}")
    print(f"One-way turnover: {proj.turnover:.2%}")

    for name, returns in DEMO_SCENARIOS.items():
        print(f"Projected level ({name}): {project_level(universe, returns):.2f}")

    idx = [0.0012, -0.0008, 0.0021, 0.0004, -0.0011, 0.0015]
    bmk = [0.0010, -0.0005, 0.0018, 0.0006, -0.0009, 0.0012]
    exc = excess_returns(idx, bmk)
    print(f"Tracking error (annualised): {tracking_error(exc):.4%}")
    print(f"Information ratio: {information_ratio(exc):.2f}")


if __name__ == "__main__":
    main()
