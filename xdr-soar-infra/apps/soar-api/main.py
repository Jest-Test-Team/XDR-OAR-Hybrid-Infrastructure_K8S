#!/usr/bin/env python3

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from kafka import KafkaConsumer
except ImportError:  # pragma: no cover
    KafkaConsumer = None


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8085"))
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "")
KAFKA_INCIDENT_TOPIC = os.getenv("KAFKA_INCIDENT_TOPIC", "detections.incidents")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "soar-api")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
SUPABASE_INCIDENTS_URL = os.getenv("SUPABASE_INCIDENTS_URL", "").rstrip("/")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY", "")

INCIDENTS: list[dict] = []
MAX_INCIDENTS = 500
METRICS = {
    "incidents_consumed_total": 0,
    "incidents_persisted_total": 0,
    "incident_persist_failures_total": 0,
}


def json_response(handler: BaseHTTPRequestHandler, payload: dict | list, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def render_metrics() -> str:
    return "\n".join(
        [
            "# HELP soar_api_incidents_consumed_total Number of incidents consumed from Kafka.",
            "# TYPE soar_api_incidents_consumed_total counter",
            f"soar_api_incidents_consumed_total {METRICS['incidents_consumed_total']}",
            "# HELP soar_api_incidents_persisted_total Number of incidents persisted to Supabase.",
            "# TYPE soar_api_incidents_persisted_total counter",
            f"soar_api_incidents_persisted_total {METRICS['incidents_persisted_total']}",
            "# HELP soar_api_incident_persist_failures_total Number of incident persistence failures.",
            "# TYPE soar_api_incident_persist_failures_total counter",
            f"soar_api_incident_persist_failures_total {METRICS['incident_persist_failures_total']}",
        ]
    ) + "\n"


def persist_incident(incident: dict) -> bool:
    if not SUPABASE_INCIDENTS_URL:
        return False

    request = urllib.request.Request(
        SUPABASE_INCIDENTS_URL,
        data=json.dumps(incident).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "apikey": SUPABASE_API_KEY,
            "Authorization": f"Bearer {SUPABASE_API_KEY}",
            "Prefer": "return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


def store_incident(incident: dict) -> None:
    INCIDENTS.insert(0, incident)
    del INCIDENTS[MAX_INCIDENTS:]


def maybe_start_consumer() -> None:
    if not KAFKA_ENABLED or not KAFKA_BROKERS.strip() or KafkaConsumer is None:
        return
    worker = threading.Thread(target=kafka_worker, daemon=True)
    worker.start()


def kafka_worker() -> None:
    brokers = [item.strip() for item in KAFKA_BROKERS.split(",") if item.strip()]
    if not brokers:
        return

    while True:
        consumer = None
        try:
            consumer = KafkaConsumer(
                KAFKA_INCIDENT_TOPIC,
                bootstrap_servers=brokers,
                group_id=KAFKA_GROUP_ID,
                enable_auto_commit=True,
                auto_offset_reset="latest",
                value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            )
            print(f"soar-api: consuming incidents from {KAFKA_INCIDENT_TOPIC}", flush=True)

            for message in consumer:
                incident = message.value if isinstance(message.value, dict) else {}
                METRICS["incidents_consumed_total"] += 1
                store_incident(incident)
                if persist_incident(incident):
                    METRICS["incidents_persisted_total"] += 1
                elif SUPABASE_INCIDENTS_URL:
                    METRICS["incident_persist_failures_total"] += 1
        except Exception as exc:
            print(f"soar-api: kafka worker error: {exc}", flush=True)
            time.sleep(5)
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "SoarAPI/0.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path in {"/health", "/api/v1/health"}:
            json_response(
                self,
                {
                    "status": "ok",
                    "service": "soar-api",
                    "configured_backends": {
                        "kafka_brokers": KAFKA_BROKERS or None,
                        "kafka_incident_topic": KAFKA_INCIDENT_TOPIC,
                        "kafka_group_id": KAFKA_GROUP_ID,
                        "kafka_enabled": KAFKA_ENABLED,
                        "supabase_incidents_url": SUPABASE_INCIDENTS_URL or None,
                    },
                    "cached_incidents": len(INCIDENTS),
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

        if self.path == "/api/v1/incidents":
            json_response(self, INCIDENTS)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    maybe_start_consumer()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"soar-api listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
