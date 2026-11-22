"""Distributed training infrastructure: job scheduling, checkpointing,
fault recovery, multi-tenant LoRA fine-tuning and throughput profiling.

A small, deterministic simulation of the training stack behind a
fine-tuning API: a GPU cluster, a job queue, fault-tolerant checkpoint /
resume, per-tenant quotas, and a profiler that estimates step time,
throughput and cost from a parallelism plan. No real cluster, no real
GPUs — every number comes from the simulated model below, so the whole
module runs on the standard library and is fully testable.
"""
import json
import math
from dataclasses import dataclass, field

# Simulated hardware model: seconds per training step on one GPU for a
# 1B-parameter model at batch 1, before parallelism and overhead.
BASE_STEP_SECONDS = 0.9
# Communication overhead per step grows with the number of workers.
COMM_OVERHEAD_PER_WORKER = 0.02
# Cost model: dollars per GPU-hour (simulated on-demand price).
GPU_HOUR_COST = 2.50


@dataclass
class Job:
    job_id: str
    tenant: str
    kind: str  # "pretrain" | "sft" | "rl" | "lora"
    gpus: int
    steps: int
    model_params_b: float = 7.0
    lora_rank: int | None = None
    status: str = "queued"  # queued | running | succeeded | failed | recovered
    completed_steps: int = 0
    checkpoint_step: int = 0
    failures: int = 0


@dataclass
class Cluster:
    """A simulated GPU cluster: nodes of equal GPU count."""
    nodes: int
    gpus_per_node: int
    failed_nodes: set = field(default_factory=set)

    @property
    def total_gpus(self) -> int:
        return self.nodes * self.gpus_per_node

    @property
    def healthy_gpus(self) -> int:
        return (self.nodes - len(self.failed_nodes)) * self.gpus_per_node

    def fail_node(self, node: int):
        if not 0 <= node < self.nodes:
            raise ValueError(f"node {node} out of range")
        self.failed_nodes.add(node)

    def repair_node(self, node: int):
        self.failed_nodes.discard(node)


class Scheduler:
    """First-fit scheduler with per-tenant GPU quotas (multi-tenant
    isolation: one tenant cannot take the whole cluster)."""

    def __init__(self, cluster: Cluster, tenant_quota_gpus: int):
        self.cluster = cluster
        self.tenant_quota_gpus = tenant_quota_gpus
        self.queue: list[Job] = []
        self.running: list[Job] = []
        self.events: list[str] = []

    def submit(self, job: Job):
        if job.gpus <= 0:
            raise ValueError("job must request at least 1 GPU")
        if job.gpus > self.cluster.total_gpus:
            raise ValueError("job requests more GPUs than the cluster has")
        self.queue.append(job)
        self.events.append(f"submitted {job.job_id} ({job.tenant}, {job.gpus} GPUs)")

    def _tenant_running_gpus(self, tenant: str) -> int:
        return sum(j.gpus for j in self.running if j.tenant == tenant)

    def schedule(self) -> list[Job]:
        """Start queued jobs that fit in healthy GPUs and the tenant quota."""
        started = []
        free = self.cluster.healthy_gpus - sum(j.gpus for j in self.running)
        for job in list(self.queue):
            tenant_used = self._tenant_running_gpus(job.tenant)
            if job.gpus <= free and tenant_used + job.gpus <= self.tenant_quota_gpus:
                self.queue.remove(job)
                job.status = "running"
                self.running.append(job)
                free -= job.gpus
                started.append(job)
                self.events.append(f"started {job.job_id} on {job.gpus} GPUs")
        return started

    def finish(self, job: Job, success: bool = True):
        if job not in self.running:
            raise ValueError(f"job {job.job_id} is not running")
        self.running.remove(job)
        job.status = "succeeded" if success else "failed"
        job.completed_steps = job.steps if success else job.completed_steps
        self.events.append(f"{job.status} {job.job_id}")


def estimate_step_time(job: Job) -> float:
    """Seconds per step for a job: base time scales with model size and
    inversely with data-parallel workers, plus communication overhead."""
    workers = max(1, job.gpus)
    compute = BASE_STEP_SECONDS * job.model_params_b / workers
    comm = COMM_OVERHEAD_PER_WORKER * (workers - 1)
    return compute + comm


def estimate_cost(job: Job) -> float:
    """Simulated dollars for the whole job: GPU-hours * hourly price."""
    hours = estimate_step_time(job) * job.steps / 3600.0
    return hours * job.gpus * GPU_HOUR_COST


def profile(job: Job) -> dict:
    """Throughput / cost profile for a job: tokens/sec assumes a fixed
    2048-token sequence per step (simulated)."""
    step_time = estimate_step_time(job)
    return {
        "job_id": job.job_id,
        "step_seconds": round(step_time, 4),
        "tokens_per_second": round(2048.0 / step_time, 1),
        "estimated_cost_usd": round(estimate_cost(job), 2),
        "estimated_hours": round(step_time * job.steps / 3600.0, 3),
    }


class CheckpointStore:
    """JSON-backed checkpoints: {job_id: {step, loss, epoch}}."""

    def __init__(self, path: str | None = None):
        self.path = path
        self._store: dict = {}
        if path:
            try:
                with open(path) as fh:
                    self._store = json.load(fh)
            except (FileNotFoundError, json.JSONDecodeError):
                self._store = {}

    def save(self, job: Job, loss: float, epoch: int):
        self._store[job.job_id] = {
            "step": job.completed_steps, "loss": loss, "epoch": epoch,
        }
        job.checkpoint_step = job.completed_steps
        if self.path:
            with open(self.path, "w") as fh:
                json.dump(self._store, fh)

    def load(self, job_id: str) -> dict | None:
        return self._store.get(job_id)


def run_steps(job: Job, checkpoints: CheckpointStore, loss_fn,
              fail_at_step: int | None = None) -> dict:
    """Simulate a training run step by step. Checkpoints every 10 steps.
    If `fail_at_step` is set, the run fails there (node failure) and the
    caller can recover it with `recover`."""
    if job.status != "running":
        raise ValueError(f"job {job.job_id} is not running")
    while job.completed_steps < job.steps:
        job.completed_steps += 1
        if fail_at_step is not None and job.completed_steps == fail_at_step:
            job.status = "failed"
            job.failures += 1
            return {"status": "failed", "completed_steps": job.completed_steps,
                    "checkpoint_step": job.checkpoint_step}
        if job.completed_steps % 10 == 0 or job.completed_steps == job.steps:
            checkpoints.save(job, loss_fn(job.completed_steps),
                             epoch=job.completed_steps // 10)
    job.status = "succeeded"
    return {"status": "succeeded", "completed_steps": job.completed_steps,
            "checkpoint_step": job.checkpoint_step}


def recover(job: Job, checkpoints: CheckpointStore, scheduler: Scheduler) -> dict:
    """Recover a failed job: resume from its last checkpoint on healthy
    GPUs, if the tenant quota allows. Returns the resume plan."""
    if job.status != "failed":
        raise ValueError(f"job {job.job_id} did not fail; nothing to recover")
    ckpt = checkpoints.load(job.job_id)
    resume_step = ckpt["step"] if ckpt else 0
    job.completed_steps = resume_step
    job.status = "recovered"
    scheduler.queue.append(job)
    started = scheduler.schedule()
    return {"job_id": job.job_id, "resume_step": resume_step,
            "restarted": job in started, "checkpoint": ckpt}


def lora_config(rank: int, alpha: float, target_modules: list[str]) -> dict:
    """Validate and build a LoRA fine-tuning config. Rank must be a
    power of two; alpha scales the update (commonly 2x rank)."""
    if rank <= 0 or (rank & (rank - 1)) != 0:
        raise ValueError(f"LoRA rank must be a power of two, got {rank}")
    if alpha <= 0:
        raise ValueError("LoRA alpha must be positive")
    if not target_modules:
        raise ValueError("LoRA needs at least one target module")
    return {
        "rank": rank,
        "alpha": alpha,
        "scaling": alpha / rank,
        "target_modules": sorted(set(target_modules)),
        "trainable_params_pct": round(100.0 * rank / 4096.0, 3),
    }


def parallel_plan(model_params_b: float, gpus: int) -> dict:
    """Pick a parallelism plan: data-parallel shards first; model
    parallelism only when the model does not fit on one worker's
    simulated 80GB (assumes ~2 bytes/param + optimizer states)."""
    bytes_per_gpu = 80 * 1024 ** 3
    needed_bytes = model_params_b * 1e9 * 6  # weights + grads + optimizer
    shards = max(1, math.ceil(needed_bytes / bytes_per_gpu))
    if shards > gpus:
        raise ValueError(
            f"model needs {shards} shards but only {gpus} GPUs available")
    return {
        "model_params_b": model_params_b,
        "gpus": gpus,
        "model_parallel_shards": shards,
        "data_parallel_workers": gpus // shards,
        "fits": True,
    }
