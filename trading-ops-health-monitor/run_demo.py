"""End-to-end demo of the trading-ops health monitor on synthetic data."""

from ops.feed_health import check_feed
from ops.order_lifecycle import check_orders
from ops.latency_telemetry import latency_summary
from ops.incident_triage import triage
from ops.release_gate import readiness_gate


def main():
    feed = check_feed({
        "name": "equity-quotes",
        "last_update_age_s": 2,
        "received_seqs": [101, 102, 103, 104, 105],
        "quotes_per_min": 980,
        "expected_quotes_per_min": 1000,
    })
    print("feed:", feed)

    orders = check_orders([
        {"order_id": "O1", "symbol": "AAPL", "status": "acked", "last_update_s": 100},
        {"order_id": "O2", "symbol": "MSFT", "status": "filled", "last_update_s": 95},
        {"order_id": "O3", "symbol": "AAPL", "status": "new", "last_update_s": 40},
    ], now_s=130)
    print("orders:", orders)

    lat = latency_summary([4, 5, 6, 5, 7, 8, 5, 6, 42, 5], slo_ms=20)
    print("latency:", lat)

    incident = triage({"id": "INC-1", "kind": "stale-feed", "impact": "high", "urgency": "high"})
    print("incident:", incident)

    gate = readiness_gate({
        "feeds_ok": feed["status"] == "ok",
        "orders_ok": not orders["stuck"],
        "latency_ok": not lat["breach"],
        "no_open_sev1": incident["severity"] != "sev1",
        "runbooks_current": True,
    })
    print("readiness gate:", gate)


if __name__ == "__main__":
    main()
