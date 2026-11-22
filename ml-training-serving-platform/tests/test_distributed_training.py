"""Tests for distributed training: scheduler, profiling, checkpoints,
fault recovery, LoRA config, parallelism plans."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ml_platform.distributed_training import (
    CheckpointStore, Cluster, Job, Scheduler, estimate_cost,
    estimate_step_time, lora_config, parallel_plan, profile,
    recover, run_steps,
)


def _loss(step):
    return 2.0 / (1.0 + step * 0.1)


def test_cluster_healthy_gpus_after_failure():
    cluster = Cluster(nodes=4, gpus_per_node=8)
    assert cluster.total_gpus == 32
    assert cluster.healthy_gpus == 32
    cluster.fail_node(1)
    assert cluster.healthy_gpus == 24
    cluster.repair_node(1)
    assert cluster.healthy_gpus == 32
    with pytest.raises(ValueError, match="out of range"):
        cluster.fail_node(9)


def test_scheduler_first_fit_and_tenant_quota():
    cluster = Cluster(nodes=2, gpus_per_node=8)
    sched = Scheduler(cluster, tenant_quota_gpus=8)
    a = Job("a", "team-x", "sft", gpus=8, steps=10)
    b = Job("b", "team-x", "sft", gpus=8, steps=10)
    c = Job("c", "team-y", "pretrain", gpus=8, steps=10)
    sched.submit(a)
    sched.submit(b)
    sched.submit(c)
    started = sched.schedule()
    assert started == [a, c]  # b blocked by team-x quota, c fits team-y
    assert b.status == "queued"
    sched.finish(a)
    started = sched.schedule()
    assert started == [b]
    with pytest.raises(ValueError, match="more GPUs than the cluster"):
        sched.submit(Job("big", "team-x", "pretrain", gpus=99, steps=1))
    with pytest.raises(ValueError, match="at least 1 GPU"):
        sched.submit(Job("zero", "team-x", "sft", gpus=0, steps=1))


def test_step_time_scales_with_workers_and_cost():
    small = Job("s", "t", "sft", gpus=1, steps=100, model_params_b=7.0)
    big = Job("b", "t", "sft", gpus=8, steps=100, model_params_b=7.0)
    assert estimate_step_time(big) < estimate_step_time(small)
    assert estimate_cost(big) > 0
    prof = profile(small)
    assert prof["tokens_per_second"] > 0
    assert prof["estimated_hours"] == pytest.approx(
        estimate_step_time(small) * 100 / 3600.0, rel=1e-3)


def test_checkpoint_save_load_and_resume():
    store = CheckpointStore()
    job = Job("j1", "team-a", "sft", gpus=4, steps=50)
    job.status = "running"
    job.completed_steps = 30
    store.save(job, 0.5, epoch=3)
    ckpt = store.load("j1")
    assert ckpt == {"step": 30, "loss": 0.5, "epoch": 3}
    assert store.load("missing") is None


def test_run_steps_success_and_failure_recovery():
    cluster = Cluster(nodes=2, gpus_per_node=8)
    sched = Scheduler(cluster, tenant_quota_gpus=16)
    store = CheckpointStore()
    job = Job("j2", "team-a", "sft", gpus=8, steps=25)
    sched.submit(job)
    sched.schedule()
    result = run_steps(job, store, _loss, fail_at_step=15)
    assert result["status"] == "failed"
    assert result["completed_steps"] == 15
    assert result["checkpoint_step"] == 10  # last checkpoint before failure
    plan = recover(job, store, sched)
    assert plan["resume_step"] == 10
    assert plan["restarted"] is True
    assert job.status == "running"
    result = run_steps(job, store, _loss)
    assert result["status"] == "succeeded"
    assert result["completed_steps"] == 25
    sched.finish(job)
    assert job.status == "succeeded"


def test_run_steps_requires_running_job():
    store = CheckpointStore()
    job = Job("j3", "team-a", "sft", gpus=2, steps=5)
    with pytest.raises(ValueError, match="is not running"):
        run_steps(job, store, _loss)


def test_recover_requires_failed_job():
    cluster = Cluster(nodes=1, gpus_per_node=8)
    sched = Scheduler(cluster, tenant_quota_gpus=8)
    store = CheckpointStore()
    job = Job("j4", "team-a", "sft", gpus=2, steps=5)
    with pytest.raises(ValueError, match="did not fail"):
        recover(job, store, sched)


def test_lora_config_validation():
    cfg = lora_config(16, 32.0, ["q_proj", "v_proj", "q_proj"])
    assert cfg == {"rank": 16, "alpha": 32.0, "scaling": 2.0,
                   "target_modules": ["q_proj", "v_proj"],
                   "trainable_params_pct": pytest.approx(0.391, rel=1e-2)}
    with pytest.raises(ValueError, match="power of two"):
        lora_config(12, 24.0, ["q_proj"])
    with pytest.raises(ValueError, match="positive"):
        lora_config(8, 0.0, ["q_proj"])
    with pytest.raises(ValueError, match="at least one target module"):
        lora_config(8, 16.0, [])


def test_parallel_plan():
    plan = parallel_plan(7.0, 8)
    assert plan["model_parallel_shards"] == 1
    assert plan["data_parallel_workers"] == 8
    # 70B params * 6 bytes = 420GB; 80GB per GPU -> 5 shards, 1 DP worker
    plan = parallel_plan(70.0, 8)
    assert plan["model_parallel_shards"] == 5
    assert plan["data_parallel_workers"] == 1
    with pytest.raises(ValueError, match="shards"):
        parallel_plan(700.0, 2)
