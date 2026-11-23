"""Run the full ECL validation: staging, ECL, back-test, benchmark, monitoring.

Usage:  python3 run_validation.py
Writes validation_report.txt next to this script and prints a summary.
"""

from ecl_model import (
    STAGE_1,
    STAGE_2,
    STAGE_3,
    backtest,
    benchmark,
    classify_stage,
    ecl_cecl,
    ecl_ifrs9,
    monitoring_report,
    portfolio_ecl,
)
from portfolio import generate_portfolio, simulate_realised_losses


def main():
    loans = generate_portfolio(n=500, seed=42)
    realised = simulate_realised_losses(loans, seed=7)
    totals = portfolio_ecl(loans)
    test = backtest(loans, realised)
    bench = benchmark(loans, realised)
    monitor = monitoring_report(loans, realised)

    lines = [
        "EXPECTED CREDIT LOSS VALIDATION REPORT",
        "=====================================",
        "",
        f"Portfolio: {totals['total_loans']} loans, "
        f"total balance ${totals['total_balance']:,.2f}",
        "Stage counts: "
        f"Stage 1={totals['counts'][STAGE_1]}, "
        f"Stage 2={totals['counts'][STAGE_2]}, "
        f"Stage 3={totals['counts'][STAGE_3]}",
        "",
        "IFRS 9 ECL by stage:",
        f"  Stage 1 (12-month ECL):  ${totals['by_stage'][STAGE_1]:,.2f}",
        f"  Stage 2 (lifetime ECL):  ${totals['by_stage'][STAGE_2]:,.2f}",
        f"  Stage 3 (lifetime ECL):  ${totals['by_stage'][STAGE_3]:,.2f}",
        f"  IFRS 9 total ECL:        ${totals['ifrs9_total']:,.2f}",
        f"  CECL total ECL:          ${totals['cecl_total']:,.2f}",
        "",
        "Back-test (predicted IFRS 9 ECL vs realised losses):",
        f"  Predicted ECL:           ${test['predicted_ecl']:,.2f}",
        f"  Realised loss:           ${test['realised_loss']:,.2f}",
        f"  Coverage ratio:          {test['coverage_ratio']:.2f}",
        f"  MAE per loan:            ${test['mae_per_loan']:,.2f}",
        f"  Under-predicted loans:   {test['under_predicted_loans']}",
        f"  Breach:                  {test['breach']}",
        "",
        "Benchmark (primary PD model vs score-band challenger):",
        f"  Primary MAE:             ${bench['primary_mae']:,.2f}",
        f"  Challenger MAE:          ${bench['challenger_mae']:,.2f}",
        f"  Winner:                  {bench['winner']}",
        "",
        "Monitoring:",
        f"  Stage 2 share:           {monitor['stage2_share']:.1%}",
        f"  Stage 3 share:           {monitor['stage3_share']:.1%}",
        f"  Top-10 ECL share:        {monitor['top10_ecl_share']:.1%}",
        f"  Breach flags:            {len(monitor['flags'])}",
    ]
    for flag in monitor["flags"]:
        lines.append(f"    - {flag}")
    if not monitor["flags"]:
        lines.append("    - none")
    lines.append("")

    report = "\n".join(lines)
    with open("validation_report.txt", "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
