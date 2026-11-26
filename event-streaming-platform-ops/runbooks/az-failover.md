# AZ failover runbook

Applies when an entire availability zone is lost (broker health checks
failing in one AZ, or the cloud provider reports an AZ event).

## Steps

1. Confirm scope: `run_demo.py` health output, or the on-call dashboard.
   Check whether the failure is one broker or a whole AZ.
2. Page the messaging-platform on-call if any partition is leaderless.
3. Promote replicas: for each affected partition, the next live replica
   becomes leader (see `messaging.dr.simulate_az_failure`). Verify no
   partition is left without a live replica.
4. Check consumer lag for every group; if lag is above the critical
   threshold (10,000), scale consumers before doing anything else.
5. Drain dead-letter queues: inspect `order-notifications-dlq` and
   `inventory-alerts-dlq`, fix the cause, then redrive.
6. Restore the AZ when the provider reports it healthy; brokers rejoin
   and replicas rebuild (about 30 minutes per the DR estimate).
7. Post-incident: file a review note with the failover time, messages
   affected, and any DLQ redrives.

## Recovery targets

- RTO: 5 minutes for leader promotion; 35 minutes including replica rebuild.
- RPO: 0 for committed records (replication factor 3, min in-sync replicas 2).
