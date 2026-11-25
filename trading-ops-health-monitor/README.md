# Trading Ops Health Monitor

A portfolio project for a Trading Operations Engineer role: health
monitoring, incident triage and operational controls for a trading
platform — market-data feed health, order lifecycle checks, latency
telemetry, incident triage with runbooks, and a pre-open readiness
gate. Built with Python standard library only.

**Demo project. Synthetic data only. Not a real production platform.**
Nothing here claims a live trading system, real market data, real
orders, or real incident history.

## Skills used

Only skills Dharma has verified: Python, SQL, Linux, Bash, Jenkins /
GitLab CI, Kubernetes, Docker, AWS concepts, Pytest, Jira. This
project does **not** claim production SRE, Prometheus/Grafana,
low-latency trading, or order-management-system experience.

## What is inside

- `ops/feed_health.py` — market-data feed health: staleness,
  sequence gaps, and quote-rate drop against an expected baseline.
- `ops/order_lifecycle.py` — order lifecycle checks: stuck orders,
  unacknowledged orders, reject rate, and workflow exceptions by
  symbol.
- `ops/latency_telemetry.py` — latency percentiles (p50/p95/p99),
  breach detection against SLO thresholds, rolling-window summaries.
- `ops/incident_triage.py` — incident severity classification,
  runbook mapping, escalation path, and SLA timers by severity.
- `ops/release_gate.py` — pre-open readiness checklist: feeds up,
  orders acknowledged, latency inside SLO, no open sev-1, runbooks
  current; returns a go / no-go verdict.
- `run_demo.py` — end-to-end demo on a synthetic trading day:
  feed check, order check, latency summary, one incident triage,
  and the pre-open gate.
- `RUNBOOK.md` — incident runbook for "stale market-data feed at
  the open": triage, checks, escalation, post-incident review.

## How to run

```bash
pip install -r requirements.txt
python run_demo.py
python -m ops.feed_health
```

## Tests

```bash
PYTHONPATH=. python -m pytest -q
```
