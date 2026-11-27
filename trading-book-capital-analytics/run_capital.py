"""Demo runner: build the book, price its capital, optimise a budget."""

from capital.capital import capital, capital_by_desk, marginal_capital, return_on_capital, rwa
from capital.exposure import ead, ead_by_desk
from capital.optimisation import allocate, best_hedge
from capital.trades import Trade, build_book
from capital.validation import run_all
from capital.var_risk import book_pnl_series, risk_summary, simulate_factor_returns, pnl_explain


def main():
    book = build_book()
    print(f"book: {len(book)} synthetic cross-asset trades, "
          f"gross notional ${sum(abs(t.notional) for t in book) / 1e6:,.1f}m")
    print(f"total EAD: ${ead(book) / 1e6:,.2f}m   RWA: ${rwa(book) / 1e6:,.2f}m   "
          f"capital (8%): ${capital(book) / 1e6:,.2f}m")
    print("\nEAD / capital by desk:")
    for desk in sorted(ead_by_desk(book)):
        print(f"  {desk:12s} EAD ${ead_by_desk(book)[desk] / 1e6:8,.2f}m   "
              f"capital ${capital_by_desk(book)[desk] / 1e6:6,.2f}m")

    # Capital-budget allocation over 10 candidate trades.
    candidates = build_book(seed=99)[:10]
    budget = 2_000_000.0
    result = allocate(book, candidates, budget)
    print(f"\ncapital budget ${budget:,.0f}: chose {len(result['chosen'])} of "
          f"{len(candidates)} candidates, used ${result['capital_used']:,.0f}, "
          f"expected P&L ${result['expected_pnl']:,.0f}, "
          f"left ${result['capital_left']:,.0f}")
    for t in result["chosen"]:
        print(f"  {t.trade_id} {t.desk:12s} {t.instrument:8s} notional "
              f"${t.notional / 1e6:7,.1f}m  marginal capital "
              f"${marginal_capital(book, t):9,.0f}  RoC {return_on_capital(book, t):.3f}")

    # Capital-efficient structuring: hedge the biggest position on the
    # desk with the largest capital footprint (Commodities), where the
    # book is directionally one-sided so an offset genuinely cuts EAD.
    comm = [t for t in book if t.asset_class == "commodity"]
    biggest = max(comm, key=lambda t: abs(t.notional))
    hedge = Trade("HEDGE1", "Commodities", "commodity", "future", -biggest.notional,
                  0.0, biggest.maturity_years, biggest.supervisory_factor,
                  -2_000.0)  # near-costless offset: small carry cost only
    best = best_hedge(book, [hedge])
    if best:
        print(f"\nhedge {biggest.trade_id} ({biggest.desk} {biggest.instrument} "
              f"${biggest.notional / 1e6:,.1f}m): saves "
              f"${best['capital_saved']:,.0f} of capital at a P&L cost of "
              f"${best['pnl_cost']:,.0f} (efficiency {best['efficiency']:.2f}x)")
    else:
        print("\nno capital-saving hedge found")

    print("\nvalidation checks:")
    for name, passed, detail in run_all(book):
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")

    # VaR / P&L explain / scenarios (Quant Risk Researcher extension).
    summary = risk_summary(book)
    print(f"\nVaR on 252 simulated days: 95% VaR "
          f"${summary['var_95']:,.0f}   99% VaR ${summary['var_99']:,.0f}   "
          f"95% ES ${summary['es_95']:,.0f}")
    print(f"mean daily P&L ${summary['mean_daily_pnl']:,.0f}   "
          f"daily vol ${summary['std_daily_pnl']:,.0f}")
    print("P&L attribution by factor (share of absolute daily P&L):")
    for factor, share in sorted(summary["factor_attribution"].items(),
                                key=lambda kv: -kv[1]):
        print(f"  {factor:10s} {share:6.1%}")
    day = simulate_factor_returns(5, seed=3)[0]
    explain = pnl_explain(book, day, seed=5)
    print(f"P&L explain, sample day: total ${explain['total']:,.0f} "
          f"(carry ${explain['carry']:,.0f}, residual "
          f"${explain['residual']:,.0f})")
    print("scenario P&L:")
    for name, pnl in summary["scenarios"].items():
        print(f"  {name:24s} ${pnl:>14,.0f}")
    bt = summary["backtest_95"]
    print(f"VaR backtest (95%, 60-day window): {bt['breaches']} breaches in "
          f"{bt['tested']} days ({bt['breach_rate']:.1%} vs 5.0% expected)")


if __name__ == "__main__":
    main()
