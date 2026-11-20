import pytest

from term_structure_mbs import (
    cpr_to_smm,
    incentive_multiplier,
    monthly_cpr,
    psa_cpr,
    smm_to_cpr,
)


def test_cpr_smm_roundtrip():
    for cpr in (0.0, 0.03, 0.06, 0.25):
        assert smm_to_cpr(cpr_to_smm(cpr)) == pytest.approx(cpr)


def test_psa_ramp():
    assert psa_cpr(1) == pytest.approx(0.002)
    assert psa_cpr(15) == pytest.approx(0.030)
    assert psa_cpr(30) == pytest.approx(0.06)
    assert psa_cpr(120) == pytest.approx(0.06)
    assert psa_cpr(30, psa=200.0) == pytest.approx(0.12)


def test_incentive_multiplier_monotonic_and_bounded():
    wac = 0.06
    rates = [0.09, 0.07, 0.06, 0.05, 0.03]
    mults = [incentive_multiplier(wac, r) for r in rates]
    assert mults == sorted(mults)  # lower market rate -> faster prepayment
    assert incentive_multiplier(wac, wac) == pytest.approx(1.0)
    assert incentive_multiplier(wac, 0.01) <= 3.0
    assert incentive_multiplier(wac, 0.15) >= 0.30


def test_monthly_cpr_faster_when_rates_fall():
    slow = monthly_cpr(40, wac=0.06, mortgage_rate=0.075)
    fast = monthly_cpr(40, wac=0.06, mortgage_rate=0.045)
    assert fast > slow
    assert fast <= 0.50
