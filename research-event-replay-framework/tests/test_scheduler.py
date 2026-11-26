"""Tests for the Slurm-style scheduler."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from replay.scheduler import Cluster, Scheduler


def test_submit_and_schedule_fifo():
    sched = Scheduler(Cluster(total_cpus=4, total_mem_gb=16))
    j1 = sched.submit("replay-a", cpus=2, mem_gb=8, command="run a")
    j2 = sched.submit("replay-b", cpus=2, mem_gb=8, command="run b")
    started = sched.schedule()
    assert started == [j1, j2]
    assert j1.state == "RUNNING" and j2.state == "RUNNING"
    assert sched.status()["used_cpus"] == 4


def test_oversubscribed_job_waits():
    sched = Scheduler(Cluster(total_cpus=4, total_mem_gb=16))
    j1 = sched.submit("big", cpus=4, mem_gb=16, command="run big")
    j2 = sched.submit("small", cpus=1, mem_gb=1, command="run small")
    sched.schedule()
    assert j1.state == "RUNNING" and j2.state == "PENDING"
    sched.finish(j1, success=True)
    assert sched.schedule() == [j2]
    assert j2.state == "RUNNING"


def test_failed_job_retries_then_fails():
    sched = Scheduler(Cluster(total_cpus=4, total_mem_gb=16))
    job = sched.submit("flaky", cpus=1, mem_gb=1, command="run flaky",
                       max_retries=1)
    sched.schedule()
    sched.finish(job, success=False)
    assert job.state == "PENDING" and job.attempts == 1
    sched.schedule()
    sched.finish(job, success=False)
    assert job.state == "FAILED" and job.attempts == 2


def test_job_larger_than_cluster_rejected():
    sched = Scheduler(Cluster(total_cpus=4, total_mem_gb=16))
    with pytest.raises(ValueError):
        sched.submit("too-big", cpus=8, mem_gb=16, command="run big")


def test_finish_non_running_rejected():
    sched = Scheduler(Cluster(total_cpus=4, total_mem_gb=16))
    job = sched.submit("idle", cpus=1, mem_gb=1, command="run idle")
    with pytest.raises(ValueError):
        sched.finish(job, success=True)
