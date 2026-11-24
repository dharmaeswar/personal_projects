"""LLM Inference Optimizer.

A small, self-contained toolkit for the work an inference-optimization
engineer does before a model ships on an accelerator: size a model and its
KV cache, quantize weights and check the accuracy cost, plan tensor-parallel
sharding, cost-model kernels with a roofline, and simulate continuous
batching to get latency and throughput numbers.

Everything here is a model of the problem, not a claim about real hardware:
model shapes are presets, hardware profiles are illustrative, and the
"kernels" are small pure-Python reference implementations used to check
correctness of a tiled layout against a naive one. No real accelerator,
no real model weights, no real customer data. Python standard library only.
"""

from .model import ModelConfig, PRESETS
from .quantization import quantize_int8, dequantize_int8
from .sharding import plan_tensor_parallel
from .batching import InferenceRequest, simulate
from .profiler import HardwareProfile, HARDWARE_PRESETS, profile

__all__ = [
    "ModelConfig",
    "PRESETS",
    "quantize_int8",
    "dequantize_int8",
    "plan_tensor_parallel",
    "InferenceRequest",
    "simulate",
    "HardwareProfile",
    "HARDWARE_PRESETS",
    "profile",
]
