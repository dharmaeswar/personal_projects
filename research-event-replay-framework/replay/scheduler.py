"""Slurm-style cluster job scheduler.

A small in-process model of the HPC scheduling a research platform runs
on: jobs request CPUs and memory, wait in a FIFO queue, run when resources
allow, and are retried a bounded number of times on failure. It mirrors
Slurm's sbatch/squeue semantics closely enough for researchers to test
orchestration logic without a real cluster.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Job:
    job_id: int
    name: str
    cpus: int
    mem_gb: int
    command: str
    state: str = "PENDING"  # PENDING -> RUNNING -> COMPLETED | FAILED
    attempts: int = 0
    max_retries: int = 1


@dataclass
class Cluster:
    total_cpus: int
    total_mem_gb: int


class Scheduler:
    """FIFO scheduler with resource accounting and bounded retries."""

    def __init__(self, cluster: Cluster):
        self.cluster = cluster
        self.jobs: list[Job] = []
        self._next_id = 1
        self._used_cpus = 0
        self._used_mem = 0

    def submit(self, name: str, cpus: int, mem_gb: int, command: str,
               max_retries: int = 1) -> Job:
        """Queue a job (sbatch). Jobs larger than the cluster are rejected."""
        if cpus <= 0 or mem_gb <= 0:
            raise ValueError("cpus and mem_gb must be positive")
        if cpus > self.cluster.total_cpus or mem_gb > self.cluster.total_mem_gb:
            raise ValueError(
                f"job {name} requests {cpus} CPUs / {mem_gb}GB, "
                f"cluster has {self.cluster.total_cpus} CPUs / "
                f"{self.cluster.total_mem_gb}GB"
            )
        job = Job(self._next_id, name, cpus, mem_gb, command,
                  max_retries=max_retries)
        self._next_id += 1
        self.jobs.append(job)
        return job

    def queue(self) -> list[Job]:
        """Jobs waiting to run, in submission order (squeue)."""
        return [j for j in self.jobs if j.state == "PENDING"]

    def _can_start(self, job: Job) -> bool:
        return (
            self._used_cpus + job.cpus <= self.cluster.total_cpus
            and self._used_mem + job.mem_gb <= self.cluster.total_mem_gb
        )

    def schedule(self) -> list[Job]:
        """Start every queued job that fits, in FIFO order. Returns started."""
        started: list[Job] = []
        for job in self.queue():
            if self._can_start(job):
                job.state = "RUNNING"
                job.attempts += 1
                self._used_cpus += job.cpus
                self._used_mem += job.mem_gb
                started.append(job)
        return started

    def finish(self, job: Job, success: bool) -> None:
        """Mark a running job done; free its resources, retry on failure."""
        if job.state != "RUNNING":
            raise ValueError(f"job {job.job_id} is not RUNNING")
        self._used_cpus -= job.cpus
        self._used_mem -= job.mem_gb
        if success:
            job.state = "COMPLETED"
        elif job.attempts <= job.max_retries:
            job.state = "PENDING"  # retry: back to the queue
        else:
            job.state = "FAILED"

    def status(self) -> dict:
        """Cluster snapshot: counts by state and current utilisation."""
        counts = {"PENDING": 0, "RUNNING": 0, "COMPLETED": 0, "FAILED": 0}
        for job in self.jobs:
            counts[job.state] += 1
        return {
            **counts,
            "used_cpus": self._used_cpus,
            "used_mem_gb": self._used_mem,
            "total_cpus": self.cluster.total_cpus,
            "total_mem_gb": self.cluster.total_mem_gb,
        }
