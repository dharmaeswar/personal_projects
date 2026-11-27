"""End-to-end demo: seed vehicles, run one order through its lifecycle,
then replay the event log to prove the rebuilt order matches."""

import tempfile
from pathlib import Path

from vehicle_platform.api import Service

VEHICLES = [
    {
        "vin": "1HGCM82633A004352", "make": "Honda", "model": "Civic",
        "year": 2021, "mileage": 28410, "list_price_cents": 2_450_000,
        "status": "AVAILABLE",
        "features": ["backup camera", "lane keep assist", "Apple CarPlay"],
    },
    {
        "vin": "5YJSA1E26CFF00001", "make": "Tesla", "model": "Model 3",
        "year": 2022, "mileage": 19320, "list_price_cents": 3_190_000,
        "status": "AVAILABLE",
        "features": ["autopilot", "glass roof", "heated seats"],
    },
    {
        "vin": "1C6RR7NT0MS123456", "make": "Ram", "model": "1500",
        "year": 2020, "mileage": 41200, "list_price_cents": 2_980_000,
        "status": "AVAILABLE",
        "features": ["tow package", "crew cab", "bed liner"],
    },
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        service = Service(Path(tmp))
        for vehicle in VEHICLES:
            service.seed_vehicle(vehicle)

        order, _ = service.create_order(
            {
                "order_id": "ORD-1001",
                "vin": "1HGCM82633A004352",
                "customer_id": "CUST-77",
                "list_price_cents": 2_450_000,
                "state_code": "AZ",
                "delivery_zip": "85281",
            }
        )
        print(f"Created {order['order_id']}: ${order['total_cents']/100:,.2f} total")
        for state in ("INSPECTED", "FINANCED", "DELIVERY_SCHEDULED"):
            order = service.advance_order("ORD-1001", state)
            print(f"Advanced to {order['status']}")

        rebuilt = service.replay_order("ORD-1001")
        assert rebuilt is not None
        assert rebuilt.status == "DELIVERY_SCHEDULED"
        assert rebuilt.total_cents() == order["total_cents"]
        print(f"Replay OK: {rebuilt.events_applied} events, "
              f"status {rebuilt.status}, total ${rebuilt.total_cents()/100:,.2f}")
        print("DLQ depth:", len(service.events.dlq))


if __name__ == "__main__":
    main()
