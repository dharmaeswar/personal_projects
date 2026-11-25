"""End-to-end demo: price a callable municipal bond and screen a small universe.

Builds a tax-exempt curve from synthetic par yields, prices a 5% 20-year
callable muni (callable at par in 10 years), reports yield-to-worst, OAS,
duration/DV01/key-rate durations, spread scenarios, and a relative-value
screen over a synthetic 12-bond universe. Writes ``muni_report.txt`` and
``muni_report.json`` next to this script.
"""

import json

from muni_engine import (
    MunicipalBond, TaxExemptCurve, bootstrap_curve, dv01,
    duration_convexity, key_rate_durations, option_adjusted_spread,
    price, spread_scenarios, yield_to_maturity, yield_to_worst,
    RelativeValueScreen, sector_summary, sector_relative_value,
    sales_ideas, TobStructure, funding_shock_scenarios,
    leverage_risk_summary, vmtp_cost, attribute_performance,
    performance_bridge,
)


def main():
    par_tenors = [1, 2, 3, 5, 7, 10, 20, 30]
    par_yields = [0.022, 0.024, 0.026, 0.029, 0.032, 0.035, 0.041, 0.044]
    curve = bootstrap_curve(par_tenors, par_yields)
    print("Tax-exempt zero curve (bootstrapped from synthetic par yields):")
    for t in par_tenors:
        print(f"  {t:>2}y  {curve.zero_rate(t) * 100:.3f}%")

    bond = MunicipalBond(coupon=0.05, maturity_years=20,
                         call_dates=[10.0], call_prices=[100.0])
    ytm = yield_to_maturity(bond, 104.50)
    ytw, ytw_source = yield_to_worst(bond, 104.50)
    oas = option_adjusted_spread(bond, curve, 104.50, vol=0.10)
    duration, convexity = duration_convexity(bond, ytw)
    krds = key_rate_durations(bond, curve)
    scenarios = spread_scenarios(bond, ytw)

    print(f"\n5% 20y callable muni @ 104.50: YTM {ytm*100:.3f}%, "
          f"YTW {ytw*100:.3f}% ({ytw_source})")
    print(f"OAS {oas*10000:.1f}bp | modified duration {duration:.2f} | "
          f"convexity {convexity:.1f} | DV01 ${dv01(bond, ytw):.4f} per 100 par")
    print("Key-rate durations:", {k: round(v, 2) for k, v in krds.items()})
    print("Spread scenarios (P&L per 100 par):",
          {f"{k:+d}bp": round(v, 3) for k, v in scenarios.items()})

    universe = [
        {"id": "MUNI-01", "sector": "GO", "maturity_years": 5, "coupon": 0.03,
         "rating": "AAA", "callable": False, "spread_bp": 28, "yield_pct": 2.9},
        {"id": "MUNI-02", "sector": "GO", "maturity_years": 10, "coupon": 0.04,
         "rating": "AA", "callable": True, "spread_bp": 52, "yield_pct": 3.5},
        {"id": "MUNI-03", "sector": "WATER_SEWER", "maturity_years": 20,
         "coupon": 0.05, "rating": "AA", "callable": True, "spread_bp": 71,
         "yield_pct": 4.2},
        {"id": "MUNI-04", "sector": "HOSPITAL", "maturity_years": 30,
         "coupon": 0.045, "rating": "A", "callable": True, "spread_bp": 88,
         "yield_pct": 4.6},
        {"id": "MUNI-05", "sector": "SCHOOL", "maturity_years": 7,
         "coupon": 0.035, "rating": "AAA", "callable": False, "spread_bp": 31,
         "yield_pct": 3.0},
        {"id": "MUNI-06", "sector": "TOLL_ROAD", "maturity_years": 12,
         "coupon": 0.05, "rating": "A", "callable": True, "spread_bp": 64,
         "yield_pct": 3.9},
        {"id": "MUNI-07", "sector": "GO", "maturity_years": 15, "coupon": 0.04,
         "rating": "AA", "callable": False, "spread_bp": 49, "yield_pct": 3.6},
        {"id": "MUNI-08", "sector": "HOSPITAL", "maturity_years": 25,
         "coupon": 0.05, "rating": "BBB", "callable": True, "spread_bp": 118,
         "yield_pct": 5.1},
        {"id": "MUNI-09", "sector": "GO", "maturity_years": 3, "coupon": 0.025,
         "rating": "AAA", "callable": False, "spread_bp": 22, "yield_pct": 2.6},
        {"id": "MUNI-10", "sector": "HOUSING", "maturity_years": 20,
         "coupon": 0.05, "rating": "A", "callable": True, "spread_bp": 96,
         "yield_pct": 4.8},
        {"id": "MUNI-11", "sector": "WATER_SEWER", "maturity_years": 10,
         "coupon": 0.045, "rating": "AA", "callable": True, "spread_bp": 55,
         "yield_pct": 3.7},
        {"id": "MUNI-12", "sector": "TOLL_ROAD", "maturity_years": 30,
         "coupon": 0.05, "rating": "AA", "callable": True, "spread_bp": 82,
         "yield_pct": 4.5},
        # Deliberately mispriced vs its GO peers, so the sales-ideas path
        # is exercised by the demo (mirrors the CHEAP test case).
        {"id": "MUNI-13", "sector": "GO", "maturity_years": 20,
         "coupon": 0.05, "rating": "AA", "callable": True, "spread_bp": 130,
         "yield_pct": 5.4},
    ]
    screen = RelativeValueScreen()
    screen.fit(universe)
    flagged = screen.screen(universe)
    print(f"\nRelative-value screen (R² = {screen.r_squared(universe):.3f}):")
    for row in flagged:
        print(f"  {row['id']} {row['rating']:>3} {row['maturity_years']:>2}y "
              f"spread {row['spread_bp']:>3}bp predicted "
              f"{row['predicted_spread_bp']:>6}bp residual "
              f"{row['residual_bp']:+6.1f}bp -> {row['flag']}")

    summary = sector_summary(flagged)
    sector_flagged = sector_relative_value(flagged)
    ideas = sales_ideas(flagged, top_n=3, marginal_tax_rate=0.37)
    print("\nPublic-finance sector summary (mean spread / mean residual):")
    for sector, s in summary.items():
        print(f"  {sector:<12} {s['sector_name']:<22} n={s['count']} "
              f"spread {s['mean_spread_bp']:>6.1f}bp residual "
              f"{s['mean_residual_bp']:+6.1f}bp")
    print("\nTop sales ideas (cheap vs sector peers, 37% tax bracket):")
    if ideas:
        for idea in ideas:
            print(f"  - {idea['rationale']}")
    else:
        print("  (none — no bond is cheap against its own sector peers)")

    # Leverage and funding risk: a TOB trust holding 100 par of 4.5%
    # munis, funded with 75 par of floaters at 3.0% plus 15bp of fees.
    tob = TobStructure(underlying_par=100.0, floater_par=75.0,
                       underlying_yield=0.045, floater_rate=0.030,
                       liquidity_fee_bps=10.0, remarketing_fee_bps=5.0)
    target_distribution = 1.50
    lev_summary = leverage_risk_summary(tob, target_distribution)
    shocks = funding_shock_scenarios(tob, target_distribution)
    vmtp = vmtp_cost(50.0, 0.032, remarketing_spread_bps=25.0)
    print("\nTOB leverage (100 par @ 4.5%, 75 par floaters @ 3.0% + 15bp fees):")
    print(f"  leverage {lev_summary['leverage_ratio']:.1f}x | residual yield "
          f"{lev_summary['residual_yield_pct']:.2f}% | distribution coverage "
          f"{lev_summary['distribution_coverage']:.3f} -> "
          f"{lev_summary['verdict']}")
    print("  Funding shocks (residual yield / coverage):",
          {f"{k:+d}bp": f"{v['residual_yield_pct']:.2f}% / {v['distribution_coverage']:.3f}"
           for k, v in shocks.items()})
    print(f"  VMTP leg (50 par @ 3.2% + 25bp spread): cost "
          f"${vmtp['annual_cost']:.3f} ({vmtp['cost_per_100_par']:.2f} per 100 par)")

    # Performance attribution: expected 1.20% vs realised 0.85% for the month.
    drivers = [
        {"name": "Rates", "contribution_pct": -0.20},
        {"name": "Spread", "contribution_pct": -0.10},
        {"name": "Curve", "contribution_pct": 0.05},
    ]
    attribution = attribute_performance(1.20, 0.85, drivers)
    bridge = performance_bridge(1.20, 0.85, drivers)
    print("\nPerformance attribution (expected 1.20% vs realised 0.85%):")
    print(f"  gap {attribution['gap_pct']:+.2f}% | explained "
          f"{attribution['explained_pct']:+.2f}% | unexplained "
          f"{attribution['unexplained_pct']:+.2f}% -> {attribution['verdict']}")

    report = {
        "bond": "5% 20y callable muni, callable at par in 10y, price 104.50",
        "ytm_pct": round(ytm * 100, 3), "ytw_pct": round(ytw * 100, 3),
        "ytw_source": ytw_source, "oas_bp": round(oas * 10000, 1),
        "modified_duration": round(duration, 2),
        "convexity": round(convexity, 1),
        "dv01_per_100_par": round(dv01(bond, ytw), 4),
        "key_rate_durations": {str(k): round(v, 2) for k, v in krds.items()},
        "spread_scenarios_pnl": {str(k): round(v, 3)
                                 for k, v in scenarios.items()},
        "relative_value_r2": round(screen.r_squared(universe), 3),
        "screen": flagged,
        "sector_summary": summary,
        "sector_screen": sector_flagged,
        "sales_ideas": [
            {"id": i["id"], "sector": i.get("sector", "GO"),
             "sector_residual_bp": i["sector_residual_bp"],
             "taxable_equivalent_yield_pct": i["taxable_equivalent_yield_pct"],
             "rationale": i["rationale"]} for i in ideas
        ],
        "leverage": {
            "leverage_ratio": lev_summary["leverage_ratio"],
            "residual_yield_pct": lev_summary["residual_yield_pct"],
            "distribution_coverage": lev_summary["distribution_coverage"],
            "coverage_at_plus_100bp": lev_summary["coverage_at_plus_100bp"],
            "verdict": lev_summary["verdict"],
            "funding_shocks": shocks,
            "vmtp_cost_per_100_par": vmtp["cost_per_100_par"],
        },
        "performance_attribution": {
            "expected_return_pct": attribution["expected_return_pct"],
            "realized_return_pct": attribution["realized_return_pct"],
            "gap_pct": attribution["gap_pct"],
            "explained_pct": attribution["explained_pct"],
            "unexplained_pct": attribution["unexplained_pct"],
            "verdict": attribution["verdict"],
        },
    }
    with open("muni_report.json", "w") as f:
        json.dump(report, f, indent=2)
    with open("muni_report.txt", "w") as f:
        f.write("Municipal Bond Pricing & Risk — demo report\n")
        f.write(f"YTM {report['ytm_pct']:.3f}%  YTW {report['ytw_pct']:.3f}% "
                f"({ytw_source})  OAS {report['oas_bp']:.1f}bp\n")
        f.write(f"Duration {duration:.2f}  Convexity {convexity:.1f}  "
                f"DV01 ${report['dv01_per_100_par']:.4f}\n")
        for row in flagged:
            f.write(f"{row['id']} {row['flag']} residual "
                    f"{row['residual_bp']:+.1f}bp\n")
        f.write("Sales ideas (cheap vs sector peers, 37% bracket):\n")
        for idea in ideas:
            f.write(f"- {idea['rationale']}\n")
        f.write(f"TOB leverage {lev_summary['leverage_ratio']:.1f}x | "
                f"residual yield {lev_summary['residual_yield_pct']:.2f}% | "
                f"coverage {lev_summary['distribution_coverage']:.3f} | "
                f"{lev_summary['verdict']}\n")
        f.write(f"Performance attribution: gap {attribution['gap_pct']:+.2f}% | "
                f"explained {attribution['explained_pct']:+.2f}% | unexplained "
                f"{attribution['unexplained_pct']:+.2f}% | "
                f"{attribution['verdict']}\n")
    print("\nWrote muni_report.txt and muni_report.json")


if __name__ == "__main__":
    main()
