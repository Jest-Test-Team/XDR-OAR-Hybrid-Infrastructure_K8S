#!/usr/bin/env python3

import json
import os
import time
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8082"))
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1.0.0")
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}

METRICS = {
    "accepted_events_total": 0,
    "rejected_events_total": 0,
}


def write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_routing_key(tenant_id: str, device_id: str, layer: str, category: str) -> str:
    parts = [
        tenant_id or "*",
        device_id or "*",
        layer or "*",
        category or "*",
    ]
    return "events." + ".".join(parts)


def normalize_event(headers: BaseHTTPRequestHandler, payload: dict) -> dict:
    event = dict(payload)
    event["tenant_id"] = headers.headers.get("X-Tenant-ID") or event.get("tenant_id") or ""
    event["device_id"] = headers.headers.get("X-Device-ID") or event.get("device_id") or ""
    event["agent_id"] = headers.headers.get("X-Agent-ID") or event.get("agent_id") or ""
    event["source"] = event.get("source") or "ingest_gateway"
    event["layer"] = event.get("layer") or "network"
    event["category"] = event.get("category") or "network"
    event["severity"] = str(event.get("severity") or "medium").lower()
    event["schema_version"] = event.get("schema_version") or SCHEMA_VERSION
    event["received_at"] = now_iso()

    if "event_id" not in event or not event["event_id"]:
        event["event_id"] = str(uuid.uuid4())

    if "timestamp" not in event or not event["timestamp"]:
        event["timestamp"] = event["received_at"]

    if "payload" not in event or not isinstance(event["payload"], dict):
        event["payload"] = event.get("payload") if isinstance(event.get("payload"), dict) else {}

    return event


def validate_event(event: dict) -> list[str]:
    errors = []
    for field in ("tenant_id", "device_id", "agent_id", "source", "layer", "category", "severity", "payload", "timestamp"):
        if field not in event or event[field] in ("", None):
            errors.append(f"missing {field}")
    if not isinstance(event.get("payload"), dict):
        errors.append("payload must be an object")
    if event.get("severity") not in ALLOWED_SEVERITIES:
        errors.append("invalid severity")
    risk_score = event.get("risk_score")
    if risk_score is not None:
        try:
            risk_value = float(risk_score)
            if risk_value < 0 or risk_value > 100:
                errors.append("risk_score out of range")
            else:
                event["risk_score"] = risk_value
        except (TypeError, ValueError):
            errors.append("risk_score must be numeric")
    return errors


def render_metrics() -> str:
    return "\n".join(
        [
            "# HELP ingest_gateway_accepted_events_total Number of accepted ingest events.",
            "# TYPE ingest_gateway_accepted_events_total counter",
            f"ingest_gateway_accepted_events_total {METRICS['accepted_events_total']}",
            "# HELP ingest_gateway_rejected_events_total Number of rejected ingest events.",
            "# TYPE ingest_gateway_rejected_events_total counter",
            f"ingest_gateway_rejected_events_total {METRICS['rejected_events_total']}",
        ]
    ) + "\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "IngestGateway/0.2"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            write_json(
                self,
                {
                    "status": "ok",
                    "service": "ingest-gateway",
                    "schema_version": SCHEMA_VERSION,
                    "time": int(time.time()),
                },
            )
            return
        if self.path == "/metrics":
            body = render_metrics().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/ingest":
            write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            METRICS["rejected_events_total"] += 1
            write_json(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        event = normalize_event(self, payload)
        validation_errors = validate_event(event)
        if validation_errors:
            METRICS["rejected_events_total"] += 1
            write_json(
                self,
                {
                    "error": "invalid event",
                    "details": validation_errors,
                    "event_id": event.get("event_id"),
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        METRICS["accepted_events_total"] += 1
        routing_key = build_routing_key(
            str(event.get("tenant_id", "")),
            str(event.get("device_id", "")),
            str(event.get("layer", "")),
            str(event.get("category", "")),
        )
        write_json(
            self,
            {
                "status": "accepted",
                "service": "ingest-gateway",
                "event_id": event["event_id"],
                "routing_key": routing_key,
                "received_at": event["received_at"],
                "event": event,
            },
            HTTPStatus.ACCEPTED,
        )


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ingest-gateway listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
