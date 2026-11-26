# Serverless Python Runtime

A small, honest model of what a Languages and Runtimes team builds for
serverless Python: take a handler plus a dependency manifest, build a
size-budgeted deployment bundle with precompiled bytecode, then execute it
on a pool of warm worker processes while measuring cold starts, latency, and
resource use.

Built as the role project for the Vercel — Software Engineer, Runtimes
application (Greenhouse job 6150691004). The JD's core work is improving
serverless Python execution: dependency management, runtime behavior,
startup performance, and resource efficiency. This project does each of
those, at single-machine scale, in standard-library Python.

## What it does

- **Dependency packaging** (`runtime/packaging.py`) — parses a
  requirements-style manifest, resolves versions against a deterministic
  index, copies the handler and dependencies into a bundle directory,
  precompiles every `.py` file to `.pyc` at build time, and rejects the
  bundle when it exceeds its size budget.
- **Warm-worker execution** (`runtime/worker.py`, `runtime/agent.py`) — each
  worker is a long-lived subprocess. The first invocation imports the
  handler (the cold start, timed); later invocations reuse the loaded
  module (warm). A handler that exceeds its timeout is killed, not left
  hanging, and a handler error is reported as data, not a runtime crash.
- **Bounded pool** (`runtime/executor.py`) — one worker per
  (handler, function) pair up to a configured concurrency limit; the pool
  refuses new workers past the limit instead of queueing without bound.
- **Observability** (`runtime/observability.py`) — per-invocation metrics
  (count, cold starts, failures, p50/p95/max latency), structured JSON-lines
  logs, and a timing span helper.
- **Configuration** (`runtime/config.py`) — the execution envelope
  (memory, timeout, concurrency, bundle budget, Python version) is validated
  up front; invalid envelopes are rejected before anything runs.
- **Infrastructure as code** (`infra/main.tf`) — a Terraform example that
  declares the runtime service the way a team would deploy it.

## Usage

```bash
# Build a deployment bundle (250 MB budget by default)
python -m runtime.cli package examples/handler.py requirements.txt --out bundle/

# Invoke the example handler once
python -m runtime.cli invoke examples/handler.py handle --event '{"name": "Ada"}'

# Invoke 5 times and print the metrics summary (1 cold + 4 warm)
python -m runtime.cli bench examples/handler.py handle --count 5

# Full end-to-end demo
python run_demo.py
```

## Test results

- **27 passed, 0 failed** (pytest; run `python -m pytest -q`).
- Demo run (`python run_demo.py`): bundle of 1,752,708 bytes within the
  250 MB budget, 2 dependencies resolved, 1 cold invocation followed by
  3 warm invocations, metrics summary with 1 cold start and 0 failures.
- One real behavior the tests pinned down: cold starts are per
  (handler, function) worker, so a second function in the same handler file
  gets its own cold start in its own worker — the first version of the
  executor test assumed one cold start per handler and was corrected to
  match the real behavior.

## Honest limits

- Single machine, not a distributed platform: no multi-region replication,
  no real sandboxing, no cgroup memory enforcement (timeouts are enforced;
  memory limits are declared in config, not enforced on the worker).
- The dependency index is a small deterministic stand-in (`FAKE_INDEX` in
  `runtime/packaging.py`), not PyPI; dependency placeholder files stand in
  for installed package contents, and sizes come from the index.
- Workers are plain subprocesses: no seccomp, no user namespacing, no
  container isolation. The Terraform file is an example declaration, not a
  tested deployment.
- Written in Python only. The Vercel role also asks for practical Rust
  experience, which this project does not demonstrate — see the application
  package notes for that gap.
- All data is synthetic; nothing describes real Vercel traffic, customers,
  or systems.
