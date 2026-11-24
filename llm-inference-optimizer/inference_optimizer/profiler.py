"""End-to-end profiler: does a model fit, and how fast does it serve?

Combines the shape model with an illustrative hardware profile. For one
decode step at a given batch size the profiler computes weight memory,
KV-cache memory, whether the model fits, a roofline latency estimate, and
throughput. ``compare_configs`` runs the same check across dtype and
tensor-parallel choices so an engineer can see the trade-off: INT8 halves
the memory and the weight-read time, sharding splits the weights but adds
all-reduce traffic.
"""

from dataclasses import dataclass

from .model import ModelConfig
from .sharding import plan_tensor_parallel

GIB = 1024 ** 3


@dataclass(frozen=True)
class HardwareProfile:
    """Illustrative accelerator profile — not a real device's spec sheet."""

    name: str
    memory_gb: float
    peak_tflops: float
    bandwidth_gbs: float


HARDWARE_PRESETS = {
    "accel-16gb": HardwareProfile("accel-16gb", memory_gb=16, peak_tflops=100, bandwidth_gbs=800),
    "accel-80gb": HardwareProfile("accel-80gb", memory_gb=80, peak_tflops=300, bandwidth_gbs=2000),
}


def profile(model: ModelConfig, hardware: HardwareProfile, batch: int,
            seq_len: int, dtype_bytes=None, tp_devices: int = 1):
    """Profile one decode step for ``model`` on ``hardware``.

    Returns a dict with weight/KV memory in GiB, whether the model fits,
    the roofline latency per step in ms, and throughput in tokens/second.
    """
    if batch <= 0 or seq_len <= 0:
        raise ValueError("batch and seq_len must be positive")
    db = dtype_bytes if dtype_bytes is not None else model.dtype_bytes
    plan = plan_tensor_parallel(model, tp_devices) if tp_devices > 1 else None
    weight_bytes = model.weight_bytes(db)
    if plan is not None:
        weight_bytes = plan.params_per_device * db
    weight_gb = weight_bytes / GIB
    kv_gb = model.kv_gb(batch, seq_len, db)
    if plan is not None:
        kv_gb = kv_gb / tp_devices
    total_gb = weight_gb + kv_gb
    fits = total_gb <= hardware.memory_gb
    # One decode step: compute is batch * flops/token; traffic is one
    # weight read plus the KV read for the batch, plus all-reduce traffic.
    compute_flops = batch * model.flops_per_token()
    traffic_bytes = weight_bytes + batch * seq_len * model.kv_bytes_per_token(db)
    if plan is not None:
        traffic_bytes += batch * plan.comm_bytes_per_token
    compute_ms = compute_flops / (hardware.peak_tflops * 1e12) * 1000
    memory_ms = traffic_bytes / (hardware.bandwidth_gbs * 1e9) * 1000
    latency_ms = max(compute_ms, memory_ms)
    throughput = batch / (latency_ms / 1000) if latency_ms > 0 else 0.0
    return {
        "model": model.name,
        "hardware": hardware.name,
        "dtype_bytes": db,
        "tp_devices": tp_devices,
        "weight_gb": round(weight_gb, 3),
        "kv_gb": round(kv_gb, 3),
        "total_gb": round(total_gb, 3),
        "fits": fits,
        "latency_ms_per_step": round(latency_ms, 3),
        "throughput_tokens_per_sec": round(throughput, 1),
        "bound": "compute" if compute_ms >= memory_ms else "memory",
    }


def compare_configs(model, hardware, batch, seq_len, candidates):
    """Rank (dtype_bytes, tp_devices) candidates by throughput.

    ``candidates`` is a list of ``(dtype_bytes, tp_devices)`` tuples.
    Only configs that fit are ranked; the rest are reported as not fitting.
    """
    ranked = []
    for dtype_bytes, tp_devices in candidates:
        result = profile(model, hardware, batch, seq_len,
                         dtype_bytes=dtype_bytes, tp_devices=tp_devices)
        ranked.append(result)
    fitting = [r for r in ranked if r["fits"]]
    fitting.sort(key=lambda r: r["throughput_tokens_per_sec"], reverse=True)
    return fitting + [r for r in ranked if not r["fits"]]
