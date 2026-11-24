"""Tensor-parallel sharding plans.

A model that does not fit on one device, or that needs more compute than
one device has, is sharded across devices. In tensor parallelism each
device holds a slice of every layer: a share of the attention heads and a
share of the MLP intermediate dimension. After each sharded matmul the
devices exchange partial results (an all-reduce), so the plan also reports
the communication volume per token — the cost that limits how far sharding
scales.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ShardPlan:
    devices: int
    heads_per_device: int
    params_per_device: int
    comm_bytes_per_token: int


def plan_tensor_parallel(config, devices: int) -> ShardPlan:
    """Split ``config`` evenly across ``devices`` tensor-parallel workers.

    Requires the head count and the MLP intermediate size to divide evenly
    across devices — a plan that splits a head in half, or leaves one
    device with a bigger slice, is rejected instead of silently
    unbalanced. Communication is one all-reduce per layer over the hidden
    activations, forward pass only.
    """
    if devices <= 0:
        raise ValueError("devices must be positive")
    if config.heads % devices != 0:
        raise ValueError(
            f"{config.heads} heads do not divide evenly across {devices} devices"
        )
    if config.intermediate_size % devices != 0:
        raise ValueError(
            f"intermediate size {config.intermediate_size} does not divide "
            f"evenly across {devices} devices"
        )
    heads_per_device = config.heads // devices
    # Per-device parameters: embedding and every layer, all split evenly.
    per_layer = 4 * config.hidden * config.hidden
    per_layer += 3 * config.hidden * config.intermediate_size
    params_per_device = (
        config.vocab * config.hidden // devices
        + config.layers * per_layer // devices
        + config.hidden
    )
    # All-reduce traffic per token: each layer moves roughly two copies of
    # the hidden activations (reduce-scatter + all-gather), scaled by the
    # (devices - 1) / devices ring factor.
    comm = int(
        2 * config.layers * config.hidden * config.dtype_bytes * 2
        * (devices - 1) / devices
    )
    return ShardPlan(
        devices=devices,
        heads_per_device=heads_per_device,
        params_per_device=params_per_device,
        comm_bytes_per_token=comm,
    )
