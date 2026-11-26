# Dead-letter queue drain runbook

Applies when the health check reports messages in a dead-letter queue.

## Steps

1. Identify the queue and count: health snapshot `dead_letter_depths`.
2. Read a sample of DLQ messages. Common causes: bad payload schema,
   a downstream service returning errors, or a routing rule sending
   events the consumer cannot parse.
3. Fix the cause first (deploy the consumer fix, or correct the
   producer payload). Redriving before the fix just refills the DLQ.
4. Redrive: move messages back to the source queue with
   `Queue.redrive()` semantics — in production this is the SQS
   redrive action with a batch of 10 and a 60-second visibility
   timeout.
5. Watch the source queue depth and consumer lag for 15 minutes after
   the redrive; if the DLQ grows again, stop and escalate.
6. Record the incident: message count, root cause, fix, redrive time.
