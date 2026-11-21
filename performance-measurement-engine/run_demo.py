"""Demo: a synthetic private-markets fund quarter, end to end."""

from perf import (
    Flow, Valuation, time_weighted_return, modified_dietz, irr,
    NavPeriod, roll_forward, reconcile, chain_roll_forward,
    excess_series, FeeTerms, gross_to_net, check_value_neutrality,
)

# A synthetic fund quarter: NAV 1,000,000, a 200,000 call mid-quarter,
# a 50,000 distribution late in the quarter.
START, MID, LATE, END = 0.0, 45.0, 80.0, 90.0
START_NAV, MID_MARK, LATE_MARK, END_NAV = 1_000_000.0, 1_050_000.0, 1_280_000.0, 1_300_000.0


def main():
    flows = [Flow(MID, 200_000.0), Flow(LATE, -50_000.0)]
    marks = [Valuation(START, START_NAV), Valuation(MID, MID_MARK),
             Valuation(LATE, LATE_MARK), Valuation(END, END_NAV)]
    twr = time_weighted_return(START_NAV, END_NAV, flows, marks,
                               start_day=START, end_day=END)
    dietz = modified_dietz(START_NAV, END_NAV, flows, start_day=START, end_day=END)
    money_weighted = irr([(0.0, -1_000_000.0), (45 / 365, -200_000.0),
                          (80 / 365, 50_000.0), (90 / 365, 1_300_000.0)])
    print("TWR:             %.4f%%" % (twr * 100))
    print("Modified Dietz:  %.4f%%" % (dietz * 100))
    print("IRR (annualised): %.4f%%" % (money_weighted * 100))

    period = NavPeriod(beginning_nav=START_NAV, contributions=200_000.0,
                       distributions=50_000.0, income=30_000.0,
                       gains=120_000.0, ending_nav=END_NAV)
    residual, ok = reconcile(period)
    print("NAV roll-forward: computed %.2f, residual %.2f, reconciles: %s"
          % (roll_forward(period), residual, ok))
    chained = chain_roll_forward([period])
    print("Chained NAV:      %.2f" % chained)

    series = excess_series([0.12, 0.08, 0.10], [0.10, None, 0.08],
                           proxy_returns=[0.09, 0.07, 0.06])
    for row in series:
        print("Benchmark-relative: portfolio %.2f%% vs benchmark %.2f%% "
              "(filled: %s) -> excess %.4f%%"
              % (row["portfolio"] * 100, row["benchmark"] * 100,
                 row["filled"], row["excess"] * 100))

    bridge = gross_to_net(1_000_000.0, 100_000.0,
                          FeeTerms(management_fee_rate=0.01, carry_rate=0.20,
                                   hurdle_rate=0.08))
    print("Gross-to-net: gross %.2f%%, fee %.2f, carry %.2f, net %.2f%%"
          % (bridge["gross_return"] * 100, bridge["management_fee"],
             bridge["carry"], bridge["net_return"] * 100))

    neutral, details = check_value_neutrality(100.0, 110.0, 50.0, 0.0)
    print("Value-neutral boundary flows: %s (base %.4f%%, start %.4f%%, end %.4f%%)"
          % (neutral, details["base_twr"] * 100,
             details["start_boundary_twr"] * 100,
             details["end_boundary_twr"] * 100))


if __name__ == "__main__":
    main()
