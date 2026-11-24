"""DynamoDB Capacity Planner.

Demand forecasting, capacity planning, quota/entitlement enforcement and
fleet-event simulation for a distributed NoSQL-style database, modelled on
the problems the AWS DynamoDB Capacity & Customer Entitlement team works on.

All data is synthetic and generated locally. Nothing here claims production
DynamoDB use; the per-partition limits below are planning assumptions taken
from public DynamoDB documentation, labelled as such.
"""

__all__ = ["forecast", "capacity", "entitlement", "fleet", "report"]
__version__ = "1.0.0"
