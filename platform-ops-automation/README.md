# Platform Ops Automation

A portfolio project for a Senior DevOps Engineer role: a containerized
Python web service plus the ops automation around it — Docker, Kubernetes
manifests, CI pipelines, log analysis, load testing, an incident
runbook, and AWS platform configuration checks (EKS, Kafka, RDS Aurora,
Cloud Foundation guardrails, storage and backup).

**Demo project. Synthetic traffic only. Not a real production platform.**
Nothing here is a claim about a real production system, and no real
incident history is described.

## Skills used

Only skills Dharma has verified: Python, Docker, Kubernetes, Jenkins /
GitLab CI, Linux, AWS concepts, SQL, Terraform (used in his roles and
hackathons, confirmed Nov 18, 2026), EKS, Vault. This project does **not**
claim Ansible, Cloudflare, or Prometheus/Grafana production experience.

## What is inside

- `service/app.py` — stdlib-only web service (`http.server`, no web
  framework). Endpoints: `/` (demo page), `/health` (JSON `ok`),
  `/metrics` (Prometheus text format: request count, latency histogram,
  error count). Latency simulation via the `LATENCY_MS` env var;
  error simulation via `ERROR_RATE`.
- `run_service.py` — starts the service on `$PORT` (default 8080).
- `docker/Dockerfile` — multi-stage build, non-root user, HEALTHCHECK
  on `/health`.
- `k8s/` — deployment (3 replicas, resource requests/limits, readiness
  and liveness probes), service, CPU-based HPA, ConfigMap, ingress
  (generic `platform-ops.example.com` placeholder host).
- `ci/` — GitHub Actions workflow (test, docker build, manifest
  validation) and a Jenkinsfile (Test / Build / Validate Manifests).
  No real deploy target.
- `ops/log_analysis.py` — parses synthetic access logs, computes the
  per-minute 5xx rate, flags minutes above a threshold, and provides
  p50/p95 latency helpers.
- `ops/reliability_dashboard.py` — aggregates synthetic per-request health
  signals into an operational health summary (availability, error rate,
  p95 latency, error-budget burn, per-service breakdown) and evaluates
  alert rules. The alert-rule shape mirrors Azure Monitor-style alert
  rules as a study; no production Azure use is claimed.
- `ops/alert_tuning.py` — alert-threshold tuning (added Nov 24, 2026,
  for a Site Reliability Engineer application): replays a labelled
  per-minute metric series against candidate thresholds, scores true
  positives, false positives and missed incidents for each one, and
  recommends the threshold that detects every incident with the fewest
  false positives. Synthetic data only; no real monitoring tool is
  contacted.
- `ops/dr_check.py` — validates a disaster-recovery / failover readiness
  checklist (runbook review freshness, last failover test, backup
  verification freshness, on-call roster) and reports overall readiness.
- `ops/nosql_health.py` — checks a synthetic multi-node NoSQL cluster (nodes up, replication lag, p99 read latency, throughput headroom) and reports overall health. Demo data only; no production NoSQL experience is claimed.
- `ops/multicloud_iac.py` — validates a Terraform-style multi-cloud plan summary (resource tags, no open ingress, secrets via Vault, two-cloud redundancy), audits secret rotation freshness (90-day limit), and estimates cross-cloud transfer cost to pick the cheapest resilient path. Demo data only; no real cloud account is touched.
- `ops/gitops_drift.py` — GitOps drift detection: compares the desired
  state declared in the `k8s/` manifests with a live-state snapshot and
  reports drift in image tags, replica counts, environment variables and
- `ops/incident_response.py` — incident response for enterprise platform
  support: weekly on-call rotation, incident lifecycle (detected →
  triaged → mitigating → resolved → closed), SLA timers by severity,
  runbook steps per incident type, and ServiceNow-style ticket sync.
  resource limits, plus missing/extra resources. A rollout gate blocks a
  deploy while drift is unresolved or error-budget burn is over its limit.
  Also includes W3C `traceparent` parse/format helpers (the propagation
  format OpenTelemetry uses) for passing trace context between services.
  All live state is synthetic input; no real cluster is contacted and no
  production GitOps or observability deployment is claimed.
- `ops/host_bottleneck.py` — diagnoses a synthetic Linux host from CPU, IO wait, memory, load and disk-latency signals, answering "is it CPU? IO?" with a verdict and a next check. Demo data only.
- `ops/aws_platform_check.py` — validates a synthetic AWS platform
  config: EKS cluster (version, multi-AZ node groups, control-plane
  logging, secrets encryption, endpoint restriction), Kafka/MSK
  (broker count, replication factor, min.insync.replicas, storage
  encryption, TLS, pinned version), RDS Aurora (engine, backup
  retention, multi-AZ instances, storage encryption, deletion
  protection), Cloud Foundation guardrails (required tags, no public
  0.0.0.0/0 ingress, SSO/federation, CloudTrail) and storage/backup
  (backup plan, retention, vault encryption, recent successful backup,
  cold-storage lifecycle). Demo data only; no real AWS account or
  resource is contacted and no production AWS experience is claimed.
- `ops/load_test.py` — stdlib-only load test (urllib + threads) that
  reports totals, error rate, and p50/p95 latency. Exits non-zero with
  a clear message if the service is not running.
- `ops/fleet_systems.py` — Linux fleet systems automation for a
  data-center fleet (added Nov 24, 2026, for an Amazon SDE III System
  Development Engineering role): a host inventory (role, OS/kernel,
  packages, services), config-drift checks against a desired state,
  staged rollouts (canary 10%, then 50%, then 100%) with a CPU/memory
  health gate after each stage and automatic rollback of the failed
  stage, and a fleet summary by role and status. Demo data only; no
  real fleet is managed and no production systems-development
  experience is claimed.
- `run_fleet_demo.py` — end-to-end demo of the fleet module on a
  12-host synthetic fleet: drift report, staged rollout with a
  failing host, rollback, and fleet summary.
- `RUNBOOK.md` — incident runbook for "elevated 5xx from the web
  platform": triage, checks, rollback, post-incident review template.

## How to run

```bash
pip install -r requirements.txt
python run_service.py
# then: curl http://127.0.0.1:8080/health
#       curl http://127.0.0.1:8080/metrics
```

Docker:

```bash
docker build -f docker/Dockerfile -t platform-ops:latest .
docker run -p 8080:8080 platform-ops:latest
```

Kubernetes (demo manifests only — no cluster is provisioned here):

```bash
kubectl apply -f k8s/
```

Log analysis and load test:

```bash
python -m ops.log_analysis
python ops/load_test.py --url http://127.0.0.1:8080 --requests 100 --concurrency 10
```

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```
