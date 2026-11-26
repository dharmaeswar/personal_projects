# Event Streaming Platform Ops

A portfolio project for a **Best Buy Engineer II — Messaging, Middleware
& Cloud Platforms** role. It builds and operates the kind of platform
the role supports: a multi-broker event-streaming cluster with
EventBridge-style routing, SNS/SQS-style queues, a dead-letter queue,
Infrastructure as Code (Terraform, Ansible, Chef), health monitoring,
and disaster-recovery failover — all simulated locally.

**Demo project. Synthetic data only. No real AWS, Kafka, MSK, RabbitMQ
or IBM MQ service is called.** Nothing here is a claim about a real
production platform, and no real incident history is described.

## Skills used

Only skills Dharma has verified: Python, Bash, Linux, SQL, Terraform
(used in his roles and hackathons, confirmed Nov 18, 2026), EKS,
Kubernetes, Jenkins, Git, PyTest. Kafka event pipelines were built at
AMDOCS (Spring Boot + Kafka streaming usage events between billing and
rating systems). This project does **not** claim production Chef or
Ansible experience, production MSK/EventBridge/SQS operation, or IBM MQ
or RabbitMQ production experience — those parts are local simulations
and declarative manifests written to show how the platform is run.

## Problem statement

Application teams need reliable, event-driven communication between
services, but a messaging platform fails in specific ways: a broker
goes down, a consumer falls behind, a bad message loops forever, or a
whole availability zone is lost. Each failure needs a different answer
— replica promotion, lag alerts, a dead-letter queue, or an AZ
failover — and the platform's configuration has to be declared as code
so the same setup can be reviewed, tested and rebuilt.

This project models that platform end to end:

- **Streaming cluster** (`messaging/brokers.py`) — topics with
  partitions replicated across 3 brokers in 3 AZs; produce/consume by
  offset; consumer-group lag; under-replicated and leaderless
  partition detection.
- **Routing** (`messaging/routing.py`) — EventBridge-style event
  patterns, SNS fanout to SQS queues, RabbitMQ topic-exchange
  matching (`*` / `#`), and DLQ redrive after max receives.
- **IaC** (`iac/`) — a declarative platform manifest plus Terraform
  (MSK, SQS, SNS, EventBridge rule), Ansible (broker provisioning)
  and Chef (broker configuration) artifacts, all checked by
  `messaging/iac.py` in CI: replication ≥ 3 across 3 AZs, encryption
  at rest, retention bounds, DLQ required on every queue.
- **Health** (`messaging/health.py`) — snapshot of brokers, lag, queue
  and DLQ depths; alerts for broker down, leaderless partitions,
  consumer lag, queue depth and DLQ messages.
- **DR** (`messaging/dr.py`) — AZ failure simulation with replica
  promotion, RTO estimate (5 min promotion, +30 min rebuild), and a
  readiness check (3 AZs, RF 3, no partition confined to one AZ).
- **Runbooks** (`runbooks/`) — AZ failover and DLQ drain procedures.

## What is inside

- `messaging/brokers.py` — Kafka-style cluster, topics, partitions, lag
- `messaging/routing.py` — event patterns, fanout, queues, DLQ, exchanges
- `messaging/iac.py` — manifest, Ansible and Chef validators
- `messaging/health.py` — health snapshot, alerts, capacity report
- `messaging/dr.py` — AZ failure simulation, failover, DR readiness
- `iac/platform.yaml` — desired state (source of truth for the demo)
- `iac/terraform/main.tf` — MSK cluster, SQS queues + DLQ, SNS, rule
- `iac/ansible/playbook.yml` — broker host provisioning
- `iac/chef/recipe.rb` — broker host configuration
- `runbooks/az-failover.md`, `runbooks/dlq-drain.md`
- `run_demo.py` — full walk-through (see below)
- `tests/test_event_streaming_platform.py` — 27 tests

## Run it

```bash
pip install -r requirements.txt
python -m pytest tests/ -q        # 27 tests
python run_demo.py                # full walk-through
```

Demo output (summary): DR readiness passes; 120 synthetic order
records produced to the `orders` topic; 12 high-value order events
fanned out to the notifications queue; 1 poison message redriven to
the DLQ after 3 failed receives; 120 records consumed with lag back
to 0; an AZ failure promotes 5 partitions with 0 lost and a 5-minute
RTO; the AZ is then restored.

## Limits, stated plainly

- The cluster, queues and exchanges are in-memory Python models, not
  real Kafka/MSK/SQS/RabbitMQ. They prove the logic (partitioning,
  lag, routing, failover), not throughput or durability at scale.
- The Terraform/Ansible/Chef files are declarative artifacts for
  review and local validation; they are never applied to a real
  account by this project.
- The 5-minute RTO is the runbook estimate for leader promotion in
  this simulation, not a measured production failover time.
