"""Stdlib HTTP API for the fulfillment service.

Endpoints (all JSON):
  POST /quote            {"distance_km","duration_min","surge_multiplier"?} -> FareQuote
  POST /trips            {"rider_id","vertical","pickup_lat","pickup_lon",
                          "dropoff_lat","dropoff_lon","quote":{...},
                          "idempotency_key"?} -> Trip
  POST /trips/{id}/match -> matches + dispatches the best driver
  POST /trips/{id}/advance {"state": "pickup"|"in_progress"|"completed"}
  POST /trips/{id}/cancel  {"reason"?}
  GET  /trips/{id}       -> trip + its event history
  GET  /trips/{id}/events?after_seq=N
  GET  /report           -> reliability report per vertical

Run: python3 run_service.py  (listens on 127.0.0.1:8080)
No third-party dependencies: the service is pure stdlib, so the API runs
anywhere Python 3.11+ runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fulfillment.lifecycle import TripState
from fulfillment.matching import Driver
from fulfillment.pricing import FareQuote, quote_fare
from fulfillment.service import (
    FulfillmentService,
    NoDriverAvailableError,
    QuoteExpiredError,
    TripAlreadyTerminalError,
    TripNotFoundError,
    demo_drivers,
)

SERVICE = FulfillmentService(demo_drivers())


def _quote_from_json(data: dict) -> FareQuote:
    return FareQuote(
        base_cents=data["base_cents"],
        distance_cents=data["distance_cents"],
        time_cents=data["time_cents"],
        surge_multiplier=data["surge_multiplier"],
        total_cents=data["total_cents"],
        minimum_cents=data["minimum_cents"],
        expires_at=datetime.fromisoformat(data["expires_at"])
        if data.get("expires_at") else None,
    )


def trip_view(trip) -> dict:
    return {
        "trip_id": trip.trip_id,
        "rider_id": trip.rider_id,
        "vertical": trip.vertical,
        "state": trip.state.value,
        "driver_id": trip.driver_id,
        "fare_cents": trip.fare_cents,
        "history": [s.value for s in trip.history],
    }


def event_view(event) -> dict:
    return {
        "seq": event.seq,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "recorded_at": event.recorded_at.isoformat(),
        "detail": event.detail,
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output clean
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        try:
            if self.path == "/quote":
                data = self._body()
                quote = quote_fare(
                    float(data["distance_km"]), float(data["duration_min"]),
                    surge_multiplier=float(data.get("surge_multiplier", 1.0)))
                self._send(200, {
                    "total_cents": quote.total_cents,
                    "base_cents": quote.base_cents,
                    "distance_cents": quote.distance_cents,
                    "time_cents": quote.time_cents,
                    "surge_multiplier": quote.surge_multiplier,
                    "minimum_cents": quote.minimum_cents,
                    "expires_at": quote.expires_at.isoformat(),
                })
                return
            if self.path == "/trips":
                data = self._body()
                trip = SERVICE.request_trip(
                    data["rider_id"], data["vertical"],
                    float(data["pickup_lat"]), float(data["pickup_lon"]),
                    float(data["dropoff_lat"]), float(data["dropoff_lon"]),
                    _quote_from_json(data["quote"]),
                    idempotency_key=data.get("idempotency_key"))
                self._send(201, trip_view(trip))
                return
            parts = [p for p in self.path.split("/") if p]
            if len(parts) == 3 and parts[0] == "trips" and parts[2] == "match":
                driver = SERVICE.match_and_dispatch(parts[1])
                self._send(200, {
                    "trip": trip_view(SERVICE.get_trip(parts[1])),
                    "driver_id": driver.driver_id,
                })
                return
            if len(parts) == 3 and parts[0] == "trips" and parts[2] == "advance":
                state = TripState(self._body()["state"])
                trip = SERVICE.advance(parts[1], state)
                self._send(200, trip_view(trip))
                return
            if len(parts) == 3 and parts[0] == "trips" and parts[2] == "cancel":
                reason = self._body().get("reason", "")
                trip = SERVICE.cancel(parts[1], reason)
                self._send(200, trip_view(trip))
                return
            self._send(404, {"error": "unknown route"})
        except (KeyError, ValueError) as exc:
            self._send(400, {"error": str(exc)})
        except QuoteExpiredError as exc:
            self._send(410, {"error": str(exc)})
        except NoDriverAvailableError as exc:
            self._send(409, {"error": str(exc)})
        except TripAlreadyTerminalError as exc:
            self._send(409, {"error": str(exc)})
        except TripNotFoundError as exc:
            self._send(404, {"error": str(exc)})

    def do_GET(self):
        try:
            if self.path == "/report":
                self._send(200, SERVICE.reliability_report())
                return
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if len(parts) == 2 and parts[0] == "trips":
                trip = SERVICE.get_trip(parts[1])
                view = trip_view(trip)
                view["events"] = [event_view(e) for e in SERVICE.events.events_for(parts[1])]
                self._send(200, view)
                return
            if len(parts) == 3 and parts[0] == "trips" and parts[2] == "events":
                after = 0
                if "after_seq=" in self.path:
                    after = int(self.path.split("after_seq=")[1].split("&")[0])
                trip = SERVICE.get_trip(parts[1])
                self._send(200, {
                    "trip_id": trip.trip_id,
                    "events": [event_view(e) for e in SERVICE.events.events_for(parts[1], after)],
                })
                return
            self._send(404, {"error": "unknown route"})
        except TripNotFoundError as exc:
            self._send(404, {"error": str(exc)})


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    print(f"Fulfillment service on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    run()
