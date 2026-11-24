# LLM Inference Optimizer

A toolkit for the work an inference-optimization engineer does before an
open model ships on an accelerator: size the model and its KV cache,
quantize the weights and check the accuracy cost, plan tensor-parallel
sharding, cost-model kernels with a roofline, and simulate continuous
batching to get latency and throughput numbers.

Built as a portfolio project for an Amazon Software Development Engineer I,
Inference Models Optimization, AWS Neuron Inference application (model
enablement on Trainium: sharding, kernels, accuracy, distributed
inference). All models, hardware profiles, weights, and traffic here are
synthetic and illustrative — no real accelerator specs, no real model
weights, no real customer data. Python standard library only at runtime;
pytest for tests.

## What it does

- **Model sizing** (`inference_optimizer/model.py`) — parameter counts,
  weight memory, FLOPs per token, and KV-cache size from a model shape.
  Presets: `tiny-0.5b`, `small-2b`, `glm-4b`, `kimi-8b` (open model
  families an enablement team works with).
- **Quantization** (`inference_optimizer/quantization.py`) — symmetric
  per-tensor and per-row INT8 quantization with dequantization, max
  absolute error, cosine similarity, and an accuracy-parity check against
  a tolerance: the gate that decides whether a model may serve in INT8.
- **Sharding** (`inference_optimizer/sharding.py`) — tensor-parallel
  plans: attention heads and MLP slices split evenly across devices,
  with the all-reduce traffic per token that limits how far sharding
  scales. Uneven splits are rejected, not silently unbalanced.
- **Kernels** (`inference_optimizer/kernels.py`) — a naive matmul and a
  cache-blocked (tiled) matmul that must agree, a scaled dot-product
  attention-score reference, and a roofline model that says whether a
  kernel is compute-bound or memory-bound.
- **Continuous batching** (`inference_optimizer/batching.py`) — a
  deterministic step simulator: prefill batched up to a token budget,
  one decode token per active request per step, KV-cache blocks reserved
  per request. Reports time-to-first-token, total steps, and throughput.
- **Profiler** (`inference_optimizer/profiler.py`) — end-to-end: weight
  + KV memory, does the model fit, roofline latency per decode step, and
  throughput; `compare_configs` ranks dtype / tensor-parallel choices.
- **CLI** (`inference_optimizer/cli.py`) — `optimize` compares configs
  for a model/hardware pair; `demo` runs a small end-to-end pass.

## Why it is new — distinctness check

Checked against the closest projects already in
`dharmaeswar/personal_projects` before building:

- `ml-training-serving-platform` trains a small classifier, keeps a
  model registry, and serves it with canary rollout and drift checks.
  It serves one finished model; it never sizes, shards, quantizes, or
  profiles inference, and has no batching scheduler or kernel model.
- `model-api-gateway` is the API layer in front of hosted endpoints
  (auth, rate limiting, routing, metering, billing). It never touches
  weights, kernels, KV cache, or batching.
- `llm-rollout-toolkit` is an LLM sampling / rollout-loop library
  (chat templates, tokenizers, tool calls, graders). It runs prompts
  through a model; it never optimizes how the model itself executes.
- `llm-training-data-infrastructure` is data plumbing for training
  (catalog, ingestion, quality gates, lineage). It never serves a model.

Different idea and problem statement from every project in the repo:
making LLM inference itself faster and cheaper on an accelerator —
sharding, quantization with an accuracy gate, kernel cost models, and
continuous batching — not training, serving APIs, rollout loops, or
training data.

## Run it

```bash
python3 -m pytest tests/ -q
python3 run_demo.py
python3 -m inference_optimizer.cli optimize --model glm-4b --hardware accel-80gb --batch 8 --seq 2048
```

## Demo output

```text
Model glm-4b: 4.16B params, 7.76 GiB in fp16, 360 KiB of KV cache per token
INT8 round trip: max error 0.0043 (scale 0.0182)
Tensor-parallel TP=2: 16 heads per device, 2.08B params per device, 360 KiB all-reduce per token
4096^3 matmul roofline on accel-80gb: 0.46 ms (intensity 1365 FLOP/byte)
Best config on accel-80gb: 1-byte weights, TP=2, 3134.3 tok/s, bound by memory
Continuous batching: 128 steps, 7.5 tokens/step, max 2 requests active at once
```

## Tests

- **61 pytest tests, all passing** (`python3 -m pytest tests/ -q` from
  the project directory): model shapes (12), quantization (11),
  sharding (7), kernels (13), batching (9), profiler (9).
