# RL Trajectory Evaluation Platform

A backend service plus dashboard data for a reinforcement learning data
platform — the kind of system behind Clera's RL work: product surfaces,
backend services and internal tools that help AI research teams and external
partners create, evaluate and improve training data.

**All data is synthetic and local.** No real environments, trajectories,
partners or model results are involved. Standard library only; no model
downloads, no API calls, no database server.

## The problem

Training data for RL is only useful if the environments are sound, the
trajectories are valid, and the tasks are good. A broken reward range, an
episode that never terminates, or a task with a wrong reward quietly poisons
an eval. This platform is the checking layer: register environments,
record and inspect trajectories, review task quality, run evaluations, and
watch environment quality, collection progress and pipeline health on one
dashboard — plus a partner workflow for submitting environments and
training data, testing them, iterating on failures, and approving them.

## What it does

- **Environment registry** (`rl_platform/environments.py`) — validate and
  register environment specs (task type, observation/action schema, reward
  range, version); browse by task type, status or owner; deprecate.
- **Trajectory recording** (`rl_platform/trajectories.py`) — record episodes
  with step-order and reward-range validation; per-trajectory stats (total
  and mean reward, length, termination); list broken trajectories.
- **Task quality review** (`rl_platform/quality.py`) — five-point rubric
  (instruction clarity, solvability, reward correctness, no leakage,
  coverage); pass needs mean ≥ 4 with no item below 3; reviewer agreement
  rate; quarantine list with failing rubric items.
- **Evaluation runs** (`rl_platform/evaluation.py`) — score every
  trajectory of an environment against a reward threshold; pass rate and
  failure modes (invalid trajectory, no termination, low reward); model
  behaviour summary by task type.
- **Dashboards & observability** (`rl_platform/observability.py`) —
  environment quality scores, data-collection progress vs target, pipeline
  health (error rate, worst lag, stale feeds), all in one `dashboard()`.
- **Partner workflow** (`rl_platform/partner.py`) — submit an environment
  plus training data, test spec and rows (required fields, duplicates,
  label coverage), iterate on failures as a new version, approve passing
  submissions into the registry.
- **JSON API layer** (`rl_platform/api.py`) — framework-free request
  routing (`handle(method, path, body)` → status, payload) over the same
  services, covering environments, trajectories, evaluations, dashboard,
  submissions and reviews.

## Run it

```bash
python3 run_demo.py        # seed demo data, print the dashboard as JSON
python3 -m pytest tests/ -q
```

## Layout

```
rl_platform/
  store.py          in-memory store
  environments.py   environment registry + validation
  trajectories.py   trajectory recording + inspection
  quality.py        task quality review + rubric
  evaluation.py     evaluation runs + model behaviour summary
  observability.py  dashboards: quality, progress, pipeline health
  partner.py        partner submission / test / iterate / approve
  api.py            JSON API layer + demo seed data
tests/              pytest suite (environments, trajectories, quality,
                    evaluation, observability, partner, API)
run_demo.py         demo: seed data, print dashboard JSON
```
