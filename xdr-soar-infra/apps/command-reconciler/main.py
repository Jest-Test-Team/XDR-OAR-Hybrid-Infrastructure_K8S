#!/usr/bin/env python3

import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from kafka import KafkaConsumer, KafkaProducer
except ImportError:  # pragma: no cover
    KafkaConsumer = None
    KafkaProducer = None


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8087"))
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "")
KAFKA_LIFECYCLE_TOPIC = os.getenv("KAFKA_LIFECYCLE_TOPIC", "commands.lifecycle")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "command-reconciler")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

STATE_BY_COMMAND: dict[str, dict] = {}
RECENT_EVENTS: list[dict] = []
MAX_RECORDS = 500
METRICS = {
    "lifecycle_events_consumed_total": 0,
    "result_events_ingested_total": 0,
    "reconciled_commands_total": 0,
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
            "# HELP command_reconciler_lifecycle_events_consumed_total Number of lifecycle events consumed.",
            "# TYPE command_reconciler_lifecycle_events_consumed_total counter",
            f"command_reconciler_lifecycle_events_consumed_total {METRICS['lifecycle_events_consumed_total']}",
            "# HELP command_reconciler_result_events_ingested_total Number of ack/result events ingested.",
            "# TYPE command_reconciler_result_events_ingested_total counter",
            f"command_reconciler_result_events_ingested_total {METRICS['result_events_ingested_total']}",
            "# HELP command_reconciler_reconciled_commands_total Number of commands with tracked state.",
            "# TYPE command_reconciler_reconciled_commands_total gauge",
            f"command_reconciler_reconciled_commands_total {METRICS['reconciled_commands_total']}",
        ]
    ) + "\n"


def store_event(event: dict) -> None:
    RECENT_EVENTS.insert(0, event)
    del RECENT_EVENTS[MAX_RECORDS:]


def apply_event(event: dict) -> None:
    command_id = event.get("command_id")
    if not command_id:
        return
    current = STATE_BY_COMMAND.get(command_id, {"command_id": command_id})
    current.update(
        {
            "correlation_id": event.get("correlation_id", current.get("correlation_id")),
            "tenant_id": event.get("tenant_id", current.get("tenant_id")),
            "device_id": event.get("device_id", current.get("device_id")),
            "command_type": event.get("command_type", current.get("command_type")),
            "status": event.get("status", current.get("status")),
            "timestamp": event.get("timestamp", int(time.time())),
            "dispatch": event.get("dispatch", current.get("dispatch")),
        }
    )
    if "result" in event:
        current["result"] = event["result"]
    STATE_BY_COMMAND[command_id] = current
    METRICS["reconciled_commands_total"] = len(STATE_BY_COMMAND)
    store_event(event)


def maybe_start_worker() -> None:
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
                KAFKA_LIFECYCLE_TOPIC,
                bootstrap_servers=brokers,
                group_id=KAFKA_GROUP_ID,
                enable_auto_commit=True,
                auto_offset_reset="latest",
                value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            )
            print(f"command-reconciler: consuming {KAFKA_LIFECYCLE_TOPIC}", flush=True)

            for message in consumer:
                event = message.value if isinstance(message.value, dict) else {}
                METRICS["lifecycle_events_consumed_total"] += 1
                apply_event(event)
        except Exception as exc:
            print(f"command-reconciler: kafka worker error: {exc}", flush=True)
            time.sleep(5)
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass


def publish_event(event: dict) -> bool:
    if not KAFKA_ENABLED or not KAFKA_BROKERS.strip() or KafkaProducer is None:
        return False
    brokers = [item.strip() for item in KAFKA_BROKERS.split(",") if item.strip()]
    if not brokers:
        return False
    producer = None
    try:
        producer = KafkaProducer(
            bootstrap_servers=brokers,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            key_serializer=lambda value: value.encode("utf-8") if value else None,
        )
        key = event.get("command_id") or "unknown"
        producer.send(KAFKA_LIFECYCLE_TOPIC, key=key, value=event).get(timeout=5)
        return True
    except Exception:
        return False
    finally:
        if producer is not None:
            try:
                producer.close()
            except Exception:
                pass


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "CommandReconciler/0.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                {
                    "status": "ok",
                    "service": "command-reconciler",
                    "configured_backends": {
                        "kafka_brokers": KAFKA_BROKERS or None,
                        "kafka_lifecycle_topic": KAFKA_LIFECYCLE_TOPIC,
                        "kafka_group_id": KAFKA_GROUP_ID,
                    },
                    "tracked_commands": len(STATE_BY_COMMAND),
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

        if self.path == "/reconciliations":
            json_response(self, list(STATE_BY_COMMAND.values()))
            return

        if self.path == "/events":
            json_response(self, RECENT_EVENTS)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/ingest-result":
            json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        status = payload.get("status")
        if status not in {"acked", "completed", "failed"}:
            json_response(self, {"error": "status must be acked, completed, or failed"}, HTTPStatus.BAD_REQUEST)
            return

        event = {
            "command_id": payload.get("command_id"),
            "correlation_id": payload.get("correlation_id"),
            "tenant_id": payload.get("tenant_id"),
            "device_id": payload.get("device_id"),
            "command_type": payload.get("command_type"),
            "status": status,
            "result": payload.get("result"),
            "timestamp": int(time.time()),
            "schema_version": "1.0.0",
        }

        if not event["command_id"]:
            json_response(self, {"error": "command_id is required"}, HTTPStatus.BAD_REQUEST)
            return

        if not publish_event(event):
            json_response(self, {"error": "failed to publish lifecycle event"}, HTTPStatus.BAD_GATEWAY)
            return

        METRICS["result_events_ingested_total"] += 1
        apply_event(event)
        json_response(self, event, HTTPStatus.ACCEPTED)


def main() -> None:
    maybe_start_worker()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"command-reconciler listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
