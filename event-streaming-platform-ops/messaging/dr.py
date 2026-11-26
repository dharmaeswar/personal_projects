"""Disaster-recovery simulation: AZ/broker failure and failover.

Local simulation only. ``simulate_az_failure`` marks every broker in
an AZ down, promotes the next live replica to leader for each
affected partition, and reports what stayed available, what lost its
leader, and the estimated recovery time. Nothing here touches a real
cluster; the point is to prove the failover logic and the runbook
steps before an incident.
"""

from __future__ import annotations

from .brokers import BrokerCluster

# Minutes, from the platform runbook (see runbooks/az-failover.md).
FAILOVER_PROMOTION_MINUTES = 5
REPLICA_REBUILD_MINUTES = 30


def simulate_az_failure(cluster: BrokerCluster, az: str) -> dict:
    """Fail an AZ: mark its brokers down, promote live replicas."""
    affected = [b for b, zone in cluster.zones.items() if zone == az]
    for broker in affected:
        cluster.mark_down(broker)
    promoted: list[dict] = []
    lost: list[dict] = []
    for name, topic in cluster.topics.items():
        for part in topic.partitions:
            if part.leader in cluster.down:
                old_leader = part.leader
                live = [b for b in part.replicas
                        if b not in cluster.down]
                if live:
                    part.replicas = live + [b for b in part.replicas
                                            if b in cluster.down]
                    promoted.append({"topic": name,
                                     "partition": part.index,
                                     "new_leader": live[0],
                                     "old_leader": old_leader})
                else:
                    lost.append({"topic": name, "partition": part.index})
    return {
        "failed_az": az,
        "brokers_down": affected,
        "promoted_partitions": promoted,
        "lost_partitions": lost,
        "available": not lost,
        "estimated_rto_minutes": (FAILOVER_PROMOTION_MINUTES
                                  if not lost else
                                  FAILOVER_PROMOTION_MINUTES
                                  + REPLICA_REBUILD_MINUTES),
    }


def restore_az(cluster: BrokerCluster, az: str) -> list[str]:
    restored = [b for b, zone in cluster.zones.items() if zone == az]
    for broker in restored:
        cluster.mark_up(broker)
    return restored


def dr_readiness(cluster: BrokerCluster) -> dict:
    """Check the cluster meets the DR bar: 3 AZs, RF 3, no single
    AZ holding every replica of any partition."""
    single_az = []
    for name, topic in cluster.topics.items():
        for part in topic.partitions:
            zones = {cluster.zones[b] for b in part.replicas}
            if len(zones) < 2:
                single_az.append((name, part.index))
    return {
        "brokers": len(cluster.broker_ids),
        "availability_zones": len(set(cluster.zones.values())),
        "replication_ok": all(
            len(p.replicas) >= 3
            for t in cluster.topics.values() for p in t.partitions),
        "partitions_confined_to_one_az": single_az,
        "ready": (len(set(cluster.zones.values())) >= 3
                  and not single_az
                  and all(len(p.replicas) >= 3
                          for t in cluster.topics.values()
                          for p in t.partitions)),
    }
