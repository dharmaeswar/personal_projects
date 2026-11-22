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
    RelativeValueScreen,
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
        {"id": "MUNI-01", "maturity_years": 5, "coupon": 0.03, "rating": "AAA",
         "callable": False, "spread_bp": 28},
        {"id": "MUNI-02", "maturity_years": 10, "coupon": 0.04, "rating": "AA",
         "callable": True, "spread_bp": 52},
        {"id": "MUNI-03", "maturity_years": 20, "coupon": 0.05, "rating": "AA",
         "callable": True, "spread_bp": 71},
        {"id": "MUNI-04", "maturity_years": 30, "coupon": 0.045, "rating": "A",
         "callable": True, "spread_bp": 88},
        {"id": "MUNI-05", "maturity_years": 7, "coupon": 0.035, "rating": "AAA",
         "callable": False, "spread_bp": 31},
        {"id": "MUNI-06", "maturity_years": 12, "coupon": 0.05, "rating": "A",
         "callable": True, "spread_bp": 64},
        {"id": "MUNI-07", "maturity_years": 15, "coupon": 0.04, "rating": "AA",
         "callable": False, "spread_bp": 49},
        {"id": "MUNI-08", "maturity_years": 25, "coupon": 0.05, "rating": "BBB",
         "callable": True, "spread_bp": 118},
        {"id": "MUNI-09", "maturity_years": 3, "coupon": 0.025, "rating": "AAA",
         "callable": False, "spread_bp": 22},
        {"id": "MUNI-10", "maturity_years": 20, "coupon": 0.05, "rating": "A",
         "callable": True, "spread_bp": 96},
        {"id": "MUNI-11", "maturity_years": 10, "coupon": 0.045, "rating": "AA",
         "callable": True, "spread_bp": 55},
        {"id": "MUNI-12", "maturity_years": 30, "coupon": 0.05, "rating": "AA",
         "callable": True, "spread_bp": 82},
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
    print("\nWrote muni_report.txt and muni_report.json")


if __name__ == "__main__":
    main()
