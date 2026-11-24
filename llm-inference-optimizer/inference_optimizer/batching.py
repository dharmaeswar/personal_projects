"""Continuous batching simulator.

In production, requests do not run one at a time: a scheduler packs many
requests into each step. Prefill (reading the prompt) is batched up to a
token budget per step; decode (generating one token) runs one token per
active request per step. Each request reserves KV-cache blocks for its
full prompt + completion, so a request waits when the cache is full.

The simulator is deterministic and step-based: it reports, per request,
time-to-first-token (TTFT) and total steps, plus overall throughput. It
is a scheduling model, not a measurement of real hardware.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class InferenceRequest:
    id: str
    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self):
        if self.prompt_tokens <= 0 or self.completion_tokens <= 0:
            raise ValueError("prompt_tokens and completion_tokens must be positive")


@dataclass
class RequestResult:
    id: str
    prompt_tokens: int
    completion_tokens: int
    ttft_steps: int
    total_steps: int

    @property
    def tpot_steps(self) -> float:
        """Time per output token, in steps, after the first token."""
        decode_steps = self.total_steps - self.ttft_steps
        return decode_steps / max(1, self.completion_tokens - 1) if self.completion_tokens > 1 else 0.0


@dataclass
class BatchSimulation:
    steps: int
    results: list
    max_active: int

    def throughput_tokens_per_step(self) -> float:
        total = sum(r.prompt_tokens + r.completion_tokens for r in self.results)
        return total / self.steps if self.steps else 0.0


def simulate(requests, max_batch_tokens, kv_block_tokens, kv_blocks):
    """Run the continuous-batching simulation.

    ``max_batch_tokens`` caps prefill tokens processed in one step.
    ``kv_block_tokens`` is the tokens per KV-cache block and ``kv_blocks``
    the number of blocks available; a request reserves
    ``ceil((prompt + completion) / kv_block_tokens)`` blocks on admission
    and holds them until it finishes.
    """
    if max_batch_tokens <= 0 or kv_block_tokens <= 0 or kv_blocks <= 0:
        raise ValueError("max_batch_tokens, kv_block_tokens and kv_blocks must be positive")
    waiting = list(requests)
    active = []  # dicts: req, prefill_left, generated, ttft, blocks
    used_blocks = 0
    results = []
    step = 0
    max_active = 0
    while waiting or active:
        step += 1
        # Admit waiting requests while KV budget allows, in arrival order.
        while waiting:
            req = waiting[0]
            need = math.ceil((req.prompt_tokens + req.completion_tokens) / kv_block_tokens)
            if used_blocks + need > kv_blocks:
                break
            waiting.pop(0)
            used_blocks += need
            active.append(
                {"req": req, "prefill_left": req.prompt_tokens,
                 "generated": 0, "ttft": None, "blocks": need}
            )
        if not active:
            raise ValueError("KV cache too small to admit any request")
        max_active = max(max_active, len(active))
        finished = []
        for slot in active:
            req = slot["req"]
            if slot["prefill_left"] > 0:
                take = min(slot["prefill_left"], max_batch_tokens)
                slot["prefill_left"] -= take
                if slot["prefill_left"] == 0:
                    slot["ttft"] = step
                    slot["generated"] += 1  # first token comes with prefill
            else:
                slot["generated"] += 1
            if slot["generated"] >= req.completion_tokens:
                finished.append(slot)
        for slot in finished:
            active.remove(slot)
            used_blocks -= slot["blocks"]
            results.append(
                RequestResult(
                    id=slot["req"].id,
                    prompt_tokens=slot["req"].prompt_tokens,
                    completion_tokens=slot["req"].completion_tokens,
                    ttft_steps=slot["ttft"],
                    total_steps=step,
                )
            )
        if step > 100000:
            raise RuntimeError("simulation did not finish")
    return BatchSimulation(steps=step, results=results, max_active=max_active)
