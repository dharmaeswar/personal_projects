"""Tests for the IFRS 9 / CECL expected credit loss validation toolkit."""

import pytest

from ecl_model import (
    STAGE_1,
    STAGE_2,
    STAGE_3,
    Loan,
    backtest,
    benchmark,
    challenger_ecl,
    classify_stage,
    ecl_cecl,
    ecl_ifrs9,
    monitoring_report,
    portfolio_ecl,
)
from portfolio import generate_portfolio, simulate_realised_losses


def make_loan(**overrides):
    base = dict(
        loan_id="LN-0001",
        balance=100_000.0,
        pd_12m=0.01,
        pd_lifetime=0.04,
        lgd=0.40,
    )
    base.update(overrides)
    return Loan(**base)


# --- Staging ---


def test_healthy_loan_is_stage1():
    assert classify_stage(make_loan()) == STAGE_1


def test_30_days_past_due_is_stage2():
    assert classify_stage(make_loan(days_past_due=30)) == STAGE_2


def test_29_days_past_due_stays_stage1():
    assert classify_stage(make_loan(days_past_due=29)) == STAGE_1


def test_89_days_past_due_is_stage2():
    assert classify_stage(make_loan(days_past_due=89)) == STAGE_2


def test_90_days_past_due_is_stage3():
    assert classify_stage(make_loan(days_past_due=90)) == STAGE_3


def test_defaulted_loan_is_stage3():
    assert classify_stage(make_loan(defaulted=True)) == STAGE_3


def test_score_drop_of_100_is_stage2():
    loan = make_loan(credit_score_orig=720, credit_score_now=620)
    assert classify_stage(loan) == STAGE_2


def test_score_drop_of_99_stays_stage1():
    loan = make_loan(credit_score_orig=720, credit_score_now=621)
    assert classify_stage(loan) == STAGE_1


def test_score_improvement_stays_stage1():
    loan = make_loan(credit_score_orig=650, credit_score_now=700)
    assert classify_stage(loan) == STAGE_1


def test_stage3_beats_stage2_triggers():
    loan = make_loan(days_past_due=120, credit_score_orig=720,
                     credit_score_now=600)
    assert classify_stage(loan) == STAGE_3


# --- ECL math ---


def test_stage1_ecl_uses_12m_pd():
    assert ecl_ifrs9(make_loan()) == pytest.approx(0.01 * 0.40 * 100_000.0)


def test_stage2_ecl_uses_lifetime_pd():
    loan = make_loan(days_past_due=45)
    assert ecl_ifrs9(loan) == pytest.approx(0.04 * 0.40 * 100_000.0)


def test_stage3_ecl_uses_pd_of_one():
    loan = make_loan(days_past_due=120)
    assert ecl_ifrs9(loan) == pytest.approx(1.0 * 0.40 * 100_000.0)


def test_cecl_uses_lifetime_pd_for_stage1_loan():
    assert ecl_cecl(make_loan()) == pytest.approx(0.04 * 0.40 * 100_000.0)


def test_cecl_is_at_least_ifrs9_for_stage1():
    loan = make_loan()
    assert ecl_cecl(loan) >= ecl_ifrs9(loan)


def test_zero_lgd_gives_zero_ecl():
    assert ecl_ifrs9(make_loan(lgd=0.0)) == 0.0
    assert ecl_cecl(make_loan(lgd=0.0)) == 0.0


def test_zero_balance_gives_zero_ecl():
    assert ecl_ifrs9(make_loan(balance=0.0)) == 0.0


def test_pd_above_one_rejected():
    with pytest.raises(ValueError):
        make_loan(pd_12m=1.5)


def test_negative_balance_rejected():
    with pytest.raises(ValueError):
        make_loan(balance=-100.0)


def test_lifetime_pd_below_12m_pd_rejected():
    with pytest.raises(ValueError):
        make_loan(pd_12m=0.05, pd_lifetime=0.02)


# --- Portfolio totals ---


def test_portfolio_totals_add_up():
    loans = [
        make_loan(loan_id="A"),
        make_loan(loan_id="B", days_past_due=45),
        make_loan(loan_id="C", days_past_due=120),
    ]
    totals = portfolio_ecl(loans)
    assert totals["counts"] == {STAGE_1: 1, STAGE_2: 1, STAGE_3: 1}
    assert totals["total_loans"] == 3
    assert totals["ifrs9_total"] == pytest.approx(
        sum(ecl_ifrs9(loan) for loan in loans)
    )
    # Stage 3 IFRS 9 uses PD = 1.0, so IFRS 9 total can exceed the CECL
    # total (which uses lifetime PD everywhere). Check exact values instead.
    assert totals["ifrs9_total"] == pytest.approx(400 + 1600 + 40000)
    assert totals["cecl_total"] == pytest.approx(1600 + 1600 + 1600)


def test_empty_portfolio_totals_are_zero():
    totals = portfolio_ecl([])
    assert totals["ifrs9_total"] == 0.0
    assert totals["cecl_total"] == 0.0
    assert totals["total_loans"] == 0


# --- Challenger model ---


def test_challenger_ecl_rises_as_score_falls():
    high = challenger_ecl(make_loan(credit_score_now=750))
    low = challenger_ecl(make_loan(credit_score_now=500))
    assert low > high


def test_challenger_ecl_is_non_negative():
    assert challenger_ecl(make_loan()) >= 0.0


# --- Back-testing ---


def test_backtest_perfect_prediction_has_coverage_one():
    loan = make_loan()
    realised = {loan.loan_id: ecl_ifrs9(loan)}
    result = backtest([loan], realised)
    assert result["coverage_ratio"] == pytest.approx(1.0)
    assert result["mae_per_loan"] == pytest.approx(0.0)
    assert result["breach"] is False


def test_backtest_flags_coverage_breach():
    loan = make_loan()
    # Realised loss 10x predicted ECL -> coverage 0.10, outside [0.80, 1.25].
    realised = {loan.loan_id: ecl_ifrs9(loan) * 10}
    result = backtest([loan], realised)
    assert result["breach"] is True
    assert result["under_predicted_loans"] == 1


def test_backtest_counts_under_predicted_loans():
    loans = [make_loan(loan_id="A"), make_loan(loan_id="B")]
    realised = {"A": 0.0, "B": ecl_ifrs9(loans[1]) * 2}
    result = backtest(loans, realised)
    assert result["under_predicted_loans"] == 1


# --- Benchmark ---


def test_benchmark_names_a_winner():
    loans = generate_portfolio(n=50, seed=1)
    realised = simulate_realised_losses(loans, seed=2)
    result = benchmark(loans, realised)
    assert result["winner"] in ("primary", "challenger")
    assert result["primary_mae"] >= 0.0
    assert result["challenger_mae"] >= 0.0


def test_benchmark_mae_gap_is_absolute_difference():
    loans = generate_portfolio(n=50, seed=1)
    realised = simulate_realised_losses(loans, seed=2)
    result = benchmark(loans, realised)
    assert result["mae_gap"] == pytest.approx(
        abs(result["primary_mae"] - result["challenger_mae"])
    )


# --- Monitoring ---


def test_monitoring_flags_high_stage2_share():
    loans = [make_loan(loan_id=f"L{i}", days_past_due=45) for i in range(10)]
    loans.append(make_loan(loan_id="OK"))
    report = monitoring_report(loans, {})
    assert report["breach"] is True
    assert any("stage2_share" in flag for flag in report["flags"])


def test_monitoring_clean_portfolio_has_no_flags():
    # 30 identical loans: top-10 ECL share is 33%, under the 50% limit.
    loans = [make_loan(loan_id=f"L{i}") for i in range(30)]
    realised = {loan.loan_id: ecl_ifrs9(loan) for loan in loans}
    report = monitoring_report(loans, realised)
    assert report["flags"] == []
    assert report["breach"] is False


# --- Synthetic data ---


def test_portfolio_generation_is_deterministic():
    first = generate_portfolio(n=100, seed=42)
    second = generate_portfolio(n=100, seed=42)
    assert [loan.loan_id for loan in first] == [loan.loan_id for loan in second]
    assert [loan.balance for loan in first] == [loan.balance for loan in second]


def test_portfolio_has_all_three_stages():
    loans = generate_portfolio(n=500, seed=42)
    stages = {classify_stage(loan) for loan in loans}
    assert stages == {STAGE_1, STAGE_2, STAGE_3}


def test_portfolio_loans_are_valid():
    loans = generate_portfolio(n=200, seed=3)
    for loan in loans:
        assert 0.0 <= loan.pd_12m <= loan.pd_lifetime <= 1.0
        assert 0.0 <= loan.lgd <= 1.0
        assert loan.balance > 0


def test_realised_losses_are_deterministic():
    loans = generate_portfolio(n=100, seed=42)
    first = simulate_realised_losses(loans, seed=7)
    second = simulate_realised_losses(loans, seed=7)
    assert first == second


def test_realised_loss_never_exceeds_balance_times_lgd():
    loans = generate_portfolio(n=200, seed=5)
    realised = simulate_realised_losses(loans, seed=9)
    for loan in loans:
        assert realised[loan.loan_id] <= loan.balance * loan.lgd + 0.01
