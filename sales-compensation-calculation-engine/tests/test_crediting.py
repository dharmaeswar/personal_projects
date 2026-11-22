"""Crediting rules: owner credit, splits, non-crediting statuses, attainment."""
from datetime import date
from decimal import Decimal

import pytest

from comp_engine import credit_deal, quota_attainment
from conftest import deal


def test_full_credit_to_owner(reps):
    assert credit_deal(deal(), reps) == {"R1": Decimal("100000")}


def test_split_shares_credit(reps):
    credited = credit_deal(
        deal(split_with=("R2",), split_pct=Decimal("0.20")), reps)
    assert credited == {"R1": Decimal("80000"), "R2": Decimal("20000")}


def test_split_across_two_partners(reps):
    reps["R3"] = reps["R1"]
    credited = credit_deal(
        deal(amount="90000", split_with=("R2", "R3"), split_pct=Decimal("0.30")), reps)
    assert credited["R1"] == Decimal("63000")
    assert credited["R2"] == Decimal("13500")
    assert credited["R3"] == Decimal("13500")


def test_refunded_deal_credits_nothing(reps):
    assert credit_deal(deal(status="refunded"), reps) == {}


def test_churned_and_pending_credit_nothing(reps):
    assert credit_deal(deal(status="churned"), reps) == {}
    assert credit_deal(deal(status="pending"), reps) == {}


def test_unknown_owner_raises(reps):
    with pytest.raises(ValueError):
        credit_deal(deal(rep_id="RX"), reps)


def test_unknown_split_partner_share_is_dropped(reps):
    credited = credit_deal(
        deal(split_with=("RX",), split_pct=Decimal("0.20")), reps)
    assert credited == {"R1": Decimal("80000")}


def test_attainment_is_fraction_of_quota(reps):
    assert quota_attainment(reps["R1"], Decimal("400000")) == Decimal("0.5000")
    assert quota_attainment(reps["R1"], Decimal("1000000")) == Decimal("1.2500")


def test_zero_quota_raises(reps):
    rep = reps["R1"]
    rep = type(rep)(**{**rep.__dict__, "quota": Decimal("0")})
    with pytest.raises(ValueError):
        quota_attainment(rep, Decimal("1000"))
