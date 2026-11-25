# PostgreSQL Reliability Automation

Demo project: health checks, backup verification, and failover/DR drill
planning for PostgreSQL-style database reliability work, plus Terraform
examples for an AWS RDS PostgreSQL instance.

**Honest disclaimer: demo project, synthetic snapshots only, no live
database.** All metrics, backup files, and drill steps are synthetic.
Nothing here connects to a real PostgreSQL server, RDS instance, or
production system.

## What it does
- `dbre/health.py` — health checks over a synthetic metric snapshot
  (connection saturation, replication lag, transaction wraparound
  headroom, bloat ratio, backup freshness) returning pass/warn/fail
  against stated thresholds.
- `dbre/backup.py` — backup verification: writes a synthetic backup
  file with a JSON manifest (SHA-256 checksum + byte size) and verifies
  a backup against its manifest.
- `dbre/drill.py` — failover/DR drill planner: builds a 7-step drill
  plan with RPO/RTO targets and a drill report that blocks the drill
  when any health check fails.
- `run_checks.py` — CLI runner tying all three together.
- `terraform/` — IaC examples only (not applied): AWS RDS PostgreSQL
  instance with backup retention, a parameter group, and enhanced
  monitoring.

## Run
```bash
python run_checks.py
python -m pytest tests/ -q
```
