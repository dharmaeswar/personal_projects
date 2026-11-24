import pytest

from airload.weight_balance import (
    AircraftLimits,
    LoadItem,
    compute_weight_balance,
)


def test_empty_aircraft_cg_is_inside_envelope():
    limits = AircraftLimits()
    result = compute_weight_balance([], limits)
    assert result.total_weight_lb == 90_000.0
    assert result.cg_arm_in == pytest.approx(550.0)
    assert result.cg_percent_mac == pytest.approx(100 * (550 - 514) / 150)
    assert result.within_envelope


def test_moment_math_uses_weight_times_arm():
    item = LoadItem("cargo:FWD:AKE1", 1_000.0, 480.0)
    assert item.moment == 480_000.0


def test_negative_weight_rejected():
    with pytest.raises(ValueError):
        LoadItem("cargo:FWD:AKE1", -10.0, 480.0)


def test_overweight_plan_is_flagged():
    limits = AircraftLimits()
    # 90,000 empty + 85,000 cargo > 170,000 MTOW.
    items = [LoadItem("cargo:FWD:AKE1", 85_000.0, 480.0)]
    result = compute_weight_balance(items, limits)
    assert not result.within_envelope
    assert any("MTOW" in v for v in result.violations)


def test_aft_cg_out_of_envelope_is_flagged():
    limits = AircraftLimits()
    # Heavy load far aft pushes CG past the aft limit.
    items = [LoadItem("cargo:BULK:B1", 30_000.0, 700.0)]
    result = compute_weight_balance(items, limits)
    assert result.cg_percent_mac > result.aft_limit
    assert not result.within_envelope
    assert any("aft" in v for v in result.violations)


def test_zero_fuel_weight_limit_is_checked():
    limits = AircraftLimits()
    # 90,000 empty + 45,000 cargo = 135,000 ZFW > 130,000 MZFW.
    items = [LoadItem("cargo:FWD:AKE1", 45_000.0, 480.0)]
    result = compute_weight_balance(items, limits)
    assert any("MZFW" in v for v in result.violations)


def test_fuel_does_not_count_toward_zero_fuel_weight():
    limits = AircraftLimits()
    items = [
        LoadItem("cargo:FWD:AKE1", 10_000.0, 480.0),
        LoadItem("fuel:total", 40_000.0, 560.0),
    ]
    result = compute_weight_balance(items, limits)
    assert result.total_weight_lb == 140_000.0
    assert not any("MZFW" in v for v in result.violations)


def test_cg_limits_interpolate_with_weight():
    limits = AircraftLimits()
    fwd_low, aft_low = limits.cg_limits(100_000.0)
    fwd_mid, aft_mid = limits.cg_limits(135_000.0)
    fwd_high, aft_high = limits.cg_limits(170_000.0)
    assert (fwd_low, aft_low) == (18.0, 28.0)
    assert (fwd_high, aft_high) == (20.0, 30.0)
    assert fwd_low < fwd_mid < fwd_high
    assert aft_low < aft_mid < aft_high
