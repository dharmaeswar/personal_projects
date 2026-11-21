# Platform Ops Automation

A portfolio project for a Senior DevOps Engineer role: a containerized
Python web service plus the ops automation around it — Docker, Kubernetes
manifests, CI pipelines, log analysis, load testing, and an incident
runbook.

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
- `ops/dr_check.py` — validates a disaster-recovery / failover readiness
  checklist (runbook review freshness, last failover test, backup
  verification freshness, on-call roster) and reports overall readiness.
- `ops/nosql_health.py` — checks a synthetic multi-node NoSQL cluster (nodes up, replication lag, p99 read latency, throughput headroom) and reports overall health. Demo data only; no production NoSQL experience is claimed.
- `ops/multicloud_iac.py` — validates a Terraform-style multi-cloud plan summary (resource tags, no open ingress, secrets via Vault, two-cloud redundancy), audits secret rotation freshness (90-day limit), and estimates cross-cloud transfer cost to pick the cheapest resilient path. Demo data only; no real cloud account is touched.
- `ops/gitops_drift.py` — GitOps drift detection: compares the desired
  state declared in the `k8s/` manifests with a live-state snapshot and
  reports drift in image tags, replica counts, environment variables and
  resource limits, plus missing/extra resources. A rollout gate blocks a
  deploy while drift is unresolved or error-budget burn is over its limit.
  Also includes W3C `traceparent` parse/format helpers (the propagation
  format OpenTelemetry uses) for passing trace context between services.
  All live state is synthetic input; no real cluster is contacted and no
  production GitOps or observability deployment is claimed.
- `ops/host_bottleneck.py` — diagnoses a synthetic Linux host from CPU, IO wait, memory, load and disk-latency signals, answering "is it CPU? IO?" with a verdict and a next check. Demo data only.
- `ops/load_test.py` — stdlib-only load test (urllib + threads) that
  reports totals, error rate, and p50/p95 latency. Exits non-zero with
  a clear message if the service is not running.
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
