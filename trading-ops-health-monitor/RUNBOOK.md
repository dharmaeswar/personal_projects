# Incident runbook: stale market-data feed at the open

## Stale market-data feed
1. Confirm the feed status in the health check: staleness, sequence gaps, quote rate.
2. Check whether the gap affects one symbol set or the whole feed.
3. Tell the trading desk which symbols are affected and hold new orders on them if the desk asks.
4. Escalate to the platform on-call and the feed provider contact; log times and ticket numbers.
5. When quotes resume, confirm sequence continuity before clearing the incident.

## Stuck orders
1. List stuck and unacknowledged orders by symbol from the lifecycle check.
2. Confirm with the desk whether the orders are safe to cancel or must be worked manually.
3. Log every action with order id, time and who approved it.

## Latency breach
1. Find which window breached the SLO and whether it is still breaching.
2. Check host CPU, memory and feed latency together before blaming one cause.
3. Escalate to platform on-call if the breach lasts more than one window.

## Reject spike
1. Count rejects by symbol and by reject reason.
2. Tell the desk the affected symbols and hold further sends on them until the cause is known.

## General triage
1. Write down what is wrong, who is affected, and when it started.
2. Classify severity from impact and urgency; set the SLA timer.
3. Pick the runbook for the incident kind; escalate per severity.
4. Post-incident review: root cause, timeline, follow-up actions, owner, due date.
