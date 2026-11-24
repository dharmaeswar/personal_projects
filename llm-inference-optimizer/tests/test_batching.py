"""Tests for the continuous batching simulator."""

import pytest

from inference_optimizer.batching import InferenceRequest, simulate


def test_single_request_ttft_and_total():
    req = InferenceRequest("r1", prompt_tokens=10, completion_tokens=5)
    sim = simulate([req], max_batch_tokens=100, kv_block_tokens=16, kv_blocks=64)
    assert len(sim.results) == 1
    result = sim.results[0]
    assert result.ttft_steps == 1
    assert result.total_steps == 5


def test_chunked_prefill_delays_first_token():
    req = InferenceRequest("r1", prompt_tokens=10, completion_tokens=5)
    sim = simulate([req], max_batch_tokens=4, kv_block_tokens=16, kv_blocks=64)
    result = sim.results[0]
    assert result.ttft_steps == 3  # 4 + 4 + 2 prefill tokens
    assert result.total_steps == 7  # 3 prefill steps + 4 decode steps


def test_requests_share_steps():
    reqs = [
        InferenceRequest("a", prompt_tokens=8, completion_tokens=4),
        InferenceRequest("b", prompt_tokens=8, completion_tokens=4),
    ]
    sim = simulate(reqs, max_batch_tokens=100, kv_block_tokens=16, kv_blocks=64)
    assert sim.steps == 4
    assert sim.max_active == 2
    assert all(r.ttft_steps == 1 for r in sim.results)


def test_kv_budget_queues_later_requests():
    reqs = [
        InferenceRequest("a", prompt_tokens=64, completion_tokens=64),
        InferenceRequest("b", prompt_tokens=64, completion_tokens=64),
    ]
    # Each request needs ceil(128 / 16) = 8 blocks; only 8 exist, so b waits.
    sim = simulate(reqs, max_batch_tokens=100, kv_block_tokens=16, kv_blocks=8)
    by_id = {r.id: r for r in sim.results}
    assert by_id["a"].total_steps == 64
    assert by_id["b"].ttft_steps > by_id["a"].total_steps


def test_kv_too_small_rejected():
    req = InferenceRequest("r1", prompt_tokens=64, completion_tokens=64)
    with pytest.raises(ValueError):
        simulate([req], max_batch_tokens=100, kv_block_tokens=16, kv_blocks=4)


def test_throughput_counts_all_tokens():
    reqs = [InferenceRequest("a", prompt_tokens=10, completion_tokens=5)]
    sim = simulate(reqs, max_batch_tokens=100, kv_block_tokens=16, kv_blocks=64)
    assert sim.throughput_tokens_per_step() == pytest.approx(15 / 5)


def test_tpot_steps():
    req = InferenceRequest("r1", prompt_tokens=10, completion_tokens=5)
    sim = simulate([req], max_batch_tokens=100, kv_block_tokens=16, kv_blocks=64)
    assert sim.results[0].tpot_steps == pytest.approx(1.0)


def test_invalid_request_rejected():
    with pytest.raises(ValueError):
        InferenceRequest("bad", prompt_tokens=0, completion_tokens=5)
    with pytest.raises(ValueError):
        InferenceRequest("bad", prompt_tokens=5, completion_tokens=0)


def test_invalid_simulator_params_rejected():
    req = InferenceRequest("r1", prompt_tokens=10, completion_tokens=5)
    with pytest.raises(ValueError):
        simulate([req], max_batch_tokens=0, kv_block_tokens=16, kv_blocks=64)
    with pytest.raises(ValueError):
        simulate([req], max_batch_tokens=100, kv_block_tokens=0, kv_blocks=64)
