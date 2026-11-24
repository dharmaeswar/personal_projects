"""Tests for tensor-parallel sharding plans."""

import pytest

from inference_optimizer.model import PRESETS
from inference_optimizer.sharding import plan_tensor_parallel


def test_glm_tp2_splits_heads_evenly():
    plan = plan_tensor_parallel(PRESETS["glm-4b"], 2)
    assert plan.heads_per_device == 16
    assert plan.devices == 2


def test_params_per_device_sums_to_model():
    model = PRESETS["glm-4b"]
    plan = plan_tensor_parallel(model, 4)
    # Embedding + layers split evenly; the final norm (hidden params) is
    # replicated on every device, so the sum is slightly above the total.
    assert plan.params_per_device * 4 >= model.param_count()
    assert plan.params_per_device * 4 <= model.param_count() + model.hidden * 4


def test_tp1_has_no_communication():
    plan = plan_tensor_parallel(PRESETS["glm-4b"], 1)
    assert plan.comm_bytes_per_token == 0
    assert plan.params_per_device == PRESETS["glm-4b"].param_count()


def test_communication_grows_with_devices():
    model = PRESETS["glm-4b"]
    c2 = plan_tensor_parallel(model, 2).comm_bytes_per_token
    c4 = plan_tensor_parallel(model, 4).comm_bytes_per_token
    assert 0 < c2 < c4


def test_uneven_heads_rejected():
    with pytest.raises(ValueError):
        plan_tensor_parallel(PRESETS["glm-4b"], 3)


def test_zero_devices_rejected():
    with pytest.raises(ValueError):
        plan_tensor_parallel(PRESETS["glm-4b"], 0)


def test_tiny_model_tp4():
    plan = plan_tensor_parallel(PRESETS["tiny-0.5b"], 4)
    assert plan.heads_per_device == 4
    assert plan.params_per_device > 0
