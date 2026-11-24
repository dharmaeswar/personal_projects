"""Command-line entry point: profile a model and simulate batching.

Usage:
    python -m inference_optimizer.cli optimize --model glm-4b \
        --hardware accel-80gb --batch 8 --seq 2048
    python -m inference_optimizer.cli demo
"""

import argparse

from .model import PRESETS
from .profiler import HARDWARE_PRESETS, compare_configs, profile
from .batching import InferenceRequest, simulate


def cmd_optimize(args):
    model = PRESETS[args.model]
    hardware = HARDWARE_PRESETS[args.hardware]
    candidates = [(2, 1), (1, 1), (2, 2), (1, 2), (2, 4)]
    print(f"Model: {model.name} ({model.param_count() / 1e9:.2f}B params, "
          f"{model.weight_gb():.2f} GiB fp16)")
    print(f"Hardware: {hardware.name} ({hardware.memory_gb} GiB, "
          f"{hardware.peak_tflops} TFLOPS, {hardware.bandwidth_gbs} GB/s)")
    print(f"Batch {args.batch}, sequence {args.seq}")
    print()
    print(f"{'dtype':>6} {'TP':>3} {'weight GiB':>11} {'KV GiB':>8} "
          f"{'fits':>5} {'ms/step':>9} {'tok/s':>9} {'bound':>8}")
    for result in compare_configs(model, hardware, args.batch, args.seq, candidates):
        print(f"{result['dtype_bytes']:>6} {result['tp_devices']:>3} "
              f"{result['weight_gb']:>11} {result['kv_gb']:>8} "
              f"{str(result['fits']):>5} {result['latency_ms_per_step']:>9} "
              f"{result['throughput_tokens_per_sec']:>9} {result['bound']:>8}")
    best = compare_configs(model, hardware, args.batch, args.seq, candidates)[0]
    print()
    print(f"Best fitting config: {best['dtype_bytes']}-byte weights, "
          f"TP={best['tp_devices']}, {best['throughput_tokens_per_sec']} tok/s")


def cmd_demo(args):
    model = PRESETS["glm-4b"]
    hardware = HARDWARE_PRESETS["accel-80gb"]
    result = profile(model, hardware, batch=8, seq_len=2048, dtype_bytes=1, tp_devices=2)
    print("Profile glm-4b, INT8, TP=2, batch 8, seq 2048 on accel-80gb:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print()
    requests = [
        InferenceRequest("chat-1", prompt_tokens=512, completion_tokens=64),
        InferenceRequest("chat-2", prompt_tokens=256, completion_tokens=128),
        InferenceRequest("chat-3", prompt_tokens=1024, completion_tokens=32),
        InferenceRequest("chat-4", prompt_tokens=128, completion_tokens=256),
    ]
    sim = simulate(requests, max_batch_tokens=512, kv_block_tokens=16, kv_blocks=512)
    print(f"Continuous batching: {sim.steps} steps, max {sim.max_active} active, "
          f"{sim.throughput_tokens_per_step():.1f} tokens/step")
    for r in sim.results:
        print(f"  {r.id}: TTFT {r.ttft_steps} steps, total {r.total_steps} steps")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="inference-optimizer")
    sub = parser.add_subparsers(dest="command", required=True)
    opt = sub.add_parser("optimize", help="compare dtype / tensor-parallel configs")
    opt.add_argument("--model", choices=sorted(PRESETS), default="glm-4b")
    opt.add_argument("--hardware", choices=sorted(HARDWARE_PRESETS), default="accel-80gb")
    opt.add_argument("--batch", type=int, default=8)
    opt.add_argument("--seq", type=int, default=2048)
    opt.set_defaults(func=cmd_optimize)
    demo = sub.add_parser("demo", help="run a small end-to-end demo")
    demo.set_defaults(func=cmd_demo)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
