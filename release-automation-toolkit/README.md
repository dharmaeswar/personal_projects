# Release Automation Toolkit

A portfolio project for a backend / continuous-delivery role
(Affirm's Developer Productivity team style). It models the path
from a developer's laptop to production the way a release
engineering team would: a release-readiness gate that blocks
unsafe releases, a staged canary rollout with health gates and
automatic rollback, a SQLite release-history store, and a
human-readable release report.

**All data is synthetic and local.** No real services, releases, or
production traffic are involved, and nothing here is a claim about
any real company's systems.

## What it does

- **Release-readiness gates** (`release_automation/gates.py`) — five
  checks run over each release: unit tests passed in CI for the
  release commit, config diff present and reviewed by someone other
  than the author, migration safety (flags `DROP TABLE` /
  `DROP COLUMN` / `TRUNCATE TABLE` / `ALTER COLUMN`; additive
  changes such as new columns pass), dependency freshness (no
  package more than one major version behind latest), and a rollback
  plan that names a previous version and the steps to reach it. Any
  failed gate blocks the release and every blocking reason is listed.
- **Canary rollout simulator** (`release_automation/rollout.py`) —
  rolls out in stages (5% → 25% → 50% → 100% of traffic). After
  each stage the health gate checks error rate (max 1%), p95
  latency (max 500 ms), and success rate (min 99%). A breach at any
  stage stops the rollout and automatically rolls back to the
  previous version. Metric snapshots are supplied by the caller, so
  the promote / roll-back logic is deterministic and testable.
- **CI step runner** (`release_automation/ci_runner.py`) — runs shell
  commands through `subprocess` with a timeout, captures
  stdout/stderr, and fails fast at the first failing step. The
  runner uses it to run this project's own test suite and feed the
  real result into the unit-test gate.
- **Release history store** (`release_automation/history.py`) —
  SQLite tables `releases` (gate outcome per service + version) and
  `rollout_events` (stage promotions and rollbacks), queryable by
  service and version, with a rollback count per service.
- **Release report** (`release_automation/report.py`) — one text
  report per release: pass/fail per gate with reasons, rollout
  timeline, and rollback events.

## Results of a run

`python3 run_release.py` evaluates three demo releases from
`releases.json` (the unit-test gate runs this project's own test
suite through the CI step runner, so the gate input is real):

```
CI step: unit tests PASSED (27 passed in 0.35s)
  checkout-api v2.4.0: SHIPPED (100%)
  search-api v3.1.0: ROLLED BACK at 25%
  billing-worker v1.9.2: BLOCKED (2/5 gates)
```

- **checkout-api v2.4.0** — 5/5 gates passed; canary promoted
  through all 4 stages (5% → 25% → 50% → 100%) with error rates
  0.2–0.4%, p95 latency 180–240 ms, success 99.6–99.8%.
- **search-api v3.1.0** — 5/5 gates passed, but the 25% canary
  stage breached all three health thresholds at once (error rate
  2.4%, p95 640 ms, success 97.6%); the rollout auto-rolled back
  to v3.0.4 and ended with 0% of traffic on v3.1.0. 1 rollback event.
- **billing-worker v1.9.2** — 2/5 gates passed, blocked before any
  rollout: config reviewed by its own author, a `DROP TABLE`
  migration, and celery pinned at v3 against latest v5.

Reports land in `release_reports/` (one `.txt` per release) and the
history in `release_history/releases.db`.

## How to run

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python3 run_release.py            # demo: gates, canary rollouts, reports
python3 -m pytest -q              # 27 tests
```

## Layout

```
release_automation/
  gates.py       readiness gates (unit tests, config review,
                 migration safety, dependency freshness, rollback plan)
  rollout.py     canary rollout simulator with health gates + auto-rollback
  history.py     SQLite release history store (releases, rollout_events)
  ci_runner.py   subprocess CI step runner (timeout, fail-fast)
  report.py      release report generator (gates, timeline, rollbacks)
run_release.py   runner: CI step -> gates -> canary -> history -> reports
releases.json    demo release definitions (services, gates input, metrics)
tests/           27 pytest tests
```

## Honest limits

- The canary simulator takes metric snapshots as input; it does not
  collect metrics from a real monitoring system, and the demo
  snapshots are hand-written, not observed traffic.
- The migration check is a text heuristic over SQL keywords, not a
  real migration linter — it cannot judge whether a migration is
  actually safe against live traffic.
- The history store is local SQLite, not a shared release database;
  it records what this toolkit ran, not what any team shipped.
- The CI runner executes shell commands in a subprocess; it models
  the "run the checks" step of a pipeline, not a CI server — no
  queueing, workers, caching, or artifact storage.
- No Kubernetes, AWS, or MySQL is used or claimed here; the toolkit
  runs entirely on local Python and SQLite.
