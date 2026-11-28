import numpy as np
import pytest

from exp_platform.design import (
    sample_size_proportion,
    sample_size_continuous,
    minimum_detectable_effect,
    check_srm,
)


def test_sample_size_proportion_known_case():
    # Baseline 10%, 1pp absolute lift, 80% power: a few thousand per arm.
    n = sample_size_proportion(0.10, 0.01)
    assert 13000 < n < 16000


def test_sample_size_grows_when_mde_shrinks():
    assert (sample_size_proportion(0.10, 0.005)
            > sample_size_proportion(0.10, 0.02))


def test_sample_size_grows_with_power():
    assert (sample_size_proportion(0.10, 0.01, power=0.90)
            > sample_size_proportion(0.10, 0.01, power=0.80))


def test_sample_size_continuous_scales_with_variance():
    n1 = sample_size_continuous(1.0, 0.1)
    n2 = sample_size_continuous(2.0, 0.1)
    assert abs(n2 / n1 - 4.0) < 0.05  # variance quadruples -> n quadruples


def test_mde_inverts_sample_size():
    n = sample_size_proportion(0.10, 0.01)
    mde = minimum_detectable_effect(0.10, n)
    assert abs(mde - 0.01) < 0.0005


def test_check_srm_balanced_split_no_flag():
    out = check_srm(10000, 10000)
    assert out["srm_detected"] is False
    assert out["p_value"] > 0.5


def test_check_srm_skewed_split_flagged():
    out = check_srm(11000, 9000)
    assert out["srm_detected"] is True
    assert out["p_value"] < 0.01


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        sample_size_proportion(1.5, 0.01)
    with pytest.raises(ValueError):
        sample_size_proportion(0.10, -0.01)
    with pytest.raises(ValueError):
        sample_size_continuous(0, 0.1)
    with pytest.raises(ValueError):
        check_srm(0, 0)
