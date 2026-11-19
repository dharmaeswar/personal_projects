"""Cold-chain telemetry integration.

Ingestion pipelines for temperature-controlled logistics: device telemetry,
carrier milestones, and customer order data are mapped into shared shipment
and telemetry models, validated, and loaded into a local warehouse.
All data is synthetic and seeded; nothing here describes a real shipment.
"""

from .models import Shipment, TelemetryReading

__all__ = ["Shipment", "TelemetryReading"]
