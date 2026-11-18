# Incident Runbook — Elevated 5xx from the Web Platform

A generic, template runbook for the Platform Ops Automation demo project.
It describes how to respond to elevated 5xx errors from a containerized
web service running on Kubernetes. No incident described here has actually
happened — there is no fabricated incident history in this project.

## Trigger

Alert fires when the per-minute 5xx rate (see `ops/log_analysis.py`,
`flag_spike_minutes`, default threshold 5%) stays above threshold for
5 consecutive minutes, or when the error budget burn rate is high.

## 1. Triage (first 5 minutes)

1. Confirm the alert is real: check `/metrics` and recent access logs.
   Is the error rate actually elevated, or is the alert noisy?
2. Scope the blast radius: which endpoints, which regions / availability
   zones, what share of traffic? Check the ingress and service status.
3. Check user impact: are health checks passing? Is `/health` returning
   200 from inside the cluster?
4. Declare severity and open an incident channel; assign an incident
   commander and a note-taker.

## 2. Checks

- **Pod status**: `kubectl get pods -l app=platform-ops` — look for
  CrashLoopBackOff, restarts, or pods not ready. `kubectl describe pod`
  for events (failed probes, OOMKilled, image pull errors).
- **Logs**: `kubectl logs -l app=platform-ops --tail=200` — look for
  repeated error lines and the first time they appeared.
- **Recent deploys**: `kubectl rollout history deployment/platform-ops` —
  did the error rate start right after a deploy or config change?
- **Resource pressure**: `kubectl top pods` and the HPA status —
  is CPU or memory saturated? Is the HPA at its max replicas?
- **Dependencies**: is the failure in the service itself, or in something
  it calls (database, upstream API)? Check dependency health separately.
- **Error budget**: how much of the monthly error budget has burned in
  the last hour? A fast burn justifies a rollback sooner.

## 3. Mitigation

Pick the fastest safe option, in this order:

1. **Rollback** to the previous known-good release (see below).
2. **Scale up** replicas temporarily if the cause is load-related.
3. **Shift traffic** away from the affected pods / zone if the failure
   is localized.
4. **Disable the bad feature** via the ConfigMap flag if the failure is
   tied to a specific code path.

Do not debug in production while users are impacted — mitigate first,
investigate second.

## 4. Rollback procedure

```bash
# See the last few revisions
kubectl rollout history deployment/platform-ops

# Roll back to the previous revision
kubectl rollout undo deployment/platform-ops

# Watch the rollout
kubectl rollout status deployment/platform-ops

# Confirm the error rate drops
# (re-run ops/log_analysis.py against fresh logs, or check /metrics)
```

If the rollback does not help, the cause is probably not the latest
deploy — go back to the checks in section 2 (config, dependencies,
infrastructure) instead of rolling back further.

## 5. Communication

- Update the incident channel every 15 minutes: what we know, what we
  are doing, what we need.
- Post a user-facing status update when impact is confirmed, and again
  when it is resolved.
- Keep all updates factual; do not speculate about root cause before
  the data supports it.

## 6. Post-incident review template

| Field | Notes |
|---|---|
| Incident date / time | |
| Duration and impact | Requests affected, error rate peak |
| Detection | How was it found, how long to detect |
| Timeline | Key events, in order |
| Root cause | What actually failed, with evidence |
| Mitigation | What stopped the impact |
| Action items | Owner + due date for each fix |
| Follow-ups | Monitoring, alerting, or runbook changes |

## 7. Prevention ideas

- Add an alert on error-budget burn rate, not just raw error rate.
- Add a canary step to the deploy pipeline before full rollout.
- Keep the runbook's rollback steps tested — run a practice rollback
  in a non-production environment.
