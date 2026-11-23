"""Subscription Billing Event Platform.

A wholesale subscription billing and distribution service in the shape of
Amazon Fuse: third-party enterprises (partners) offer subscription services
through global billing partners. The platform provisions entitlements,
routes billing events through a topic/queue bus, and bills/renews/cancels
with idempotent, retry-safe handlers.

Everything is local and deterministic: the entitlement store behaves like
DynamoDB (partition + sort key, conditional writes, TTL), the event bus
behaves like SNS topics fanning out to SQS queues (deduplication, FIFO
ordering per subscriber, dead-letter queue), and the handlers behave like
Lambda functions (stateless, idempotent, retry-safe).

All data is synthetic demo data. Nothing here claims production use.
"""

from .store import EntitlementStore
from .events import EventBus
from .billing import BillingService
from .api import EntitlementLookup

__all__ = ["EntitlementStore", "EventBus", "BillingService", "EntitlementLookup"]
