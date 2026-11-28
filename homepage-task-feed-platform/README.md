# Homepage Task Feed Platform

A portfolio project for a **Senior Software Engineer, Product Foundations** role (Ramp-style): the shared platform behind a Homepage that brings work from many product teams into one ranked, actionable feed.

**All data is synthetic and seeded.** Nothing here is a claim about a real production system at Ramp or anywhere else. The code is a demo of the platform problems in the posting, built with the standard library only.

## Problem statement

Homepage is the most visited surface: finance teams land there each day to see what needs attention — approvals, receipts, account setup, recommendations. Behind it sits a shared platform that must:

- **Aggregate tasks from many teams** into one feed, with one contract: every team validates against the same task shape, bad tasks are quarantined with a reason, and re-deliveries are deduped on `(source, external_id)`.
- **Rank them** with one transparent score (priority + due-date urgency + relevance, with a freshness decay) so the most actionable work is on top, deterministically.
- **Behave consistently**: every task supports the same standard actions (approve / reject / complete / dismiss / snooze / open detail) through one state machine, and every detail view has the same shape, so product teams get new capabilities for free.
- **Stay fast and correct at scale**: each source has a latency budget; a slow source degrades to cached tasks flagged stale, a dead source fails cleanly with a notice, and one slow team can never stall the feed.
- **Run experiments honestly**: deterministic per-user assignment, completion-rate readouts, and a sample-ratio-mismatch guardrail that blocks shipping on a broken readout.

## What is inside

```
taskfeed/
  models.py        Task, DetailView, kinds, states, standard actions
  ingest.py        contract validation, dedupe, quarantine
  ranking.py       transparent score + deterministic ordering
  actions.py       state machine, idempotent actions, detail views, snooze wake-up
  latency.py       per-source budgets, p50/p95 tracking, stale-cache degradation
  experiments.py   deterministic assignment, z-test readout, SRM guardrail
  reliability.py   retry with backoff, circuit breaker
  feed.py          FeedBuilder: fetch inside budget, dedupe, rank, return feed
run_demo.py        end-to-end demo: 3 teams, one slow, one down, one experiment readout
tests/             pytest suite covering every module
```

## Run it

```bash
python3 -m pytest tests/ -q
python3 run_demo.py
```

## Honest limits

- Synthetic seeded data only; no live feed, no real users, no production traffic.
- Latency is simulated (fetch functions return an elapsed time), not measured against real services; the p95 tracker is real math over those samples.
- Ranking weights are explicit constants chosen for the demo, not fitted to real engagement data; the experiment readout uses synthetic counts.
- Single-process, in-memory caches; no persistence, no auth, no frontend. The detail view is a data structure, not a rendered page.
- No ranking/recommendation production experience is claimed: the project demonstrates the platform shape (aggregation, ranking, actions, budgets, experiments), not a deployed feed system.
