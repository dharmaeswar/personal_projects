"""Kubernetes pod-spec generation for task runs (dicts, no cluster needed)."""
from __future__ import annotations

from .dags import Dag, Task


def namespace_for(tenant: str) -> str:
    return f"wf-{tenant}"


def pod_spec(dag: Dag, task: Task, logical_date: str, attempt: int) -> dict:
    """Build the pod spec the executor would submit for one task run."""
    run_id = f"{dag.dag_id}-{logical_date}-{task.task_id}-try{attempt}"
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": run_id.lower().replace("_", "-"),
            "namespace": namespace_for(dag.tenant),
            "labels": {
                "app": "workflow-platform",
                "tenant": dag.tenant,
                "dag_id": dag.dag_id,
                "task_id": task.task_id,
            },
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [
                {
                    "name": "task",
                    "image": task.image,
                    "command": task.command,
                    "resources": {
                        "requests": {"cpu": task.cpu, "memory": task.memory},
                        "limits": {"cpu": task.cpu, "memory": task.memory},
                    },
                    "env": [
                        {"name": "TENANT", "value": dag.tenant},
                        {"name": "DAG_ID", "value": dag.dag_id},
                        {"name": "TASK_ID", "value": task.task_id},
                        {"name": "LOGICAL_DATE", "value": logical_date},
                    ],
                }
            ],
        },
    }


def resource_quota(tenant: str, max_pods: int, cpu: str, memory: str) -> dict:
    """Namespace-level ResourceQuota so one tenant cannot starve the others."""
    return {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {"name": f"{tenant}-quota", "namespace": namespace_for(tenant)},
        "spec": {
            "hard": {"pods": str(max_pods), "requests.cpu": cpu, "requests.memory": memory}
        },
    }
