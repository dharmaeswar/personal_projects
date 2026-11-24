"""Demo: size a model, quantize weights, shard it, and simulate serving.

Run from the project directory:
    python3 run_demo.py
"""

from inference_optimizer import PRESETS, quantize_int8, dequantize_int8
from inference_optimizer.batching import InferenceRequest, simulate
from inference_optimizer.kernels import KernelSpec, matmul_flops, roofline_time_ms
from inference_optimizer.profiler import HARDWARE_PRESETS, compare_configs
from inference_optimizer.sharding import plan_tensor_parallel


def main():
    model = PRESETS["glm-4b"]
    print(f"Model {model.name}: {model.param_count() / 1e9:.2f}B params, "
          f"{model.weight_gb():.2f} GiB in fp16, "
          f"{model.kv_bytes_per_token() / 1024:.0f} KiB of KV cache per token")

    weights = [0.42, -1.18, 0.07, 2.31, -0.55, 0.91]
    codes, scale = quantize_int8(weights)
    recon = dequantize_int8(codes, scale)
    print(f"INT8 round trip: max error "
          f"{max(abs(a - b) for a, b in zip(weights, recon)):.4f} "
          f"(scale {scale:.4f})")

    plan = plan_tensor_parallel(model, 2)
    print(f"Tensor-parallel TP=2: {plan.heads_per_device} heads per device, "
          f"{plan.params_per_device / 1e9:.2f}B params per device, "
          f"{plan.comm_bytes_per_token / 1024:.0f} KiB all-reduce per token")

    spec = KernelSpec("matmul-4096", flops=matmul_flops(4096, 4096, 4096),
                      bytes_moved=3 * 4096 * 4096 * 2)
    print(f"4096^3 matmul roofline on accel-80gb: "
          f"{roofline_time_ms(spec, 300, 2000):.2f} ms "
          f"(intensity {spec.arithmetic_intensity():.0f} FLOP/byte)")

    hardware = HARDWARE_PRESETS["accel-80gb"]
    best = compare_configs(model, hardware, 8, 2048,
                           [(2, 1), (1, 1), (2, 2), (1, 2)])[0]
    print(f"Best config on {hardware.name}: {best['dtype_bytes']}-byte weights, "
          f"TP={best['tp_devices']}, {best['throughput_tokens_per_sec']} tok/s, "
          f"bound by {best['bound']}")

    requests = [
        InferenceRequest("chat-1", prompt_tokens=512, completion_tokens=64),
        InferenceRequest("chat-2", prompt_tokens=256, completion_tokens=128),
    ]
    sim = simulate(requests, max_batch_tokens=512, kv_block_tokens=16, kv_blocks=512)
    print(f"Continuous batching: {sim.steps} steps, "
          f"{sim.throughput_tokens_per_step():.1f} tokens/step, "
          f"max {sim.max_active} requests active at once")


if __name__ == "__main__":
    main()
