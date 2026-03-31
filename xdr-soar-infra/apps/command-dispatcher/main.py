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
PORT = int(os.getenv("PORT", "8086"))
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "")
KAFKA_COMMAND_TOPIC = os.getenv("KAFKA_COMMAND_TOPIC", "commands.issue")
KAFKA_LIFECYCLE_TOPIC = os.getenv("KAFKA_LIFECYCLE_TOPIC", "commands.lifecycle")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "command-dispatcher")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
MQTT_TOPIC_TEMPLATE = os.getenv("MQTT_TOPIC_TEMPLATE", "jobs/commands/{device_id}")

RECENT_DISPATCHES: list[dict] = []
MAX_RECORDS = 500
METRICS = {
    "commands_consumed_total": 0,
    "commands_dispatched_total": 0,
    "dispatch_failures_total": 0,
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
            "# HELP command_dispatcher_commands_consumed_total Number of commands consumed.",
            "# TYPE command_dispatcher_commands_consumed_total counter",
            f"command_dispatcher_commands_consumed_total {METRICS['commands_consumed_total']}",
            "# HELP command_dispatcher_commands_dispatched_total Number of commands dispatched.",
            "# TYPE command_dispatcher_commands_dispatched_total counter",
            f"command_dispatcher_commands_dispatched_total {METRICS['commands_dispatched_total']}",
            "# HELP command_dispatcher_dispatch_failures_total Number of dispatch failures.",
            "# TYPE command_dispatcher_dispatch_failures_total counter",
            f"command_dispatcher_dispatch_failures_total {METRICS['dispatch_failures_total']}",
        ]
    ) + "\n"


def store_dispatch(record: dict) -> None:
    RECENT_DISPATCHES.insert(0, record)
    del RECENT_DISPATCHES[MAX_RECORDS:]


def build_dispatch_payload(command: dict) -> dict:
    device_id = command.get("device_id") or "unknown"
    topic = MQTT_TOPIC_TEMPLATE.format(device_id=device_id)
    return {
        "command_id": command.get("command_id"),
        "correlation_id": command.get("correlation_id"),
        "tenant_id": command.get("tenant_id"),
        "device_id": device_id,
        "command_type": command.get("command_type"),
        "risk_level": command.get("risk_level"),
        "requires_presence": command.get("requires_presence", False),
        "approval_required": command.get("approval_required", False),
        "payload": command.get("payload", {}),
        "dispatch_transport": "mqtt-placeholder",
        "dispatch_topic": topic,
        "dispatched_at": int(time.time()),
        "schema_version": "1.0.0",
    }


def lifecycle_event(command: dict, status: str, dispatch_payload: dict | None = None) -> dict:
    event = {
        "command_id": command.get("command_id"),
        "correlation_id": command.get("correlation_id"),
        "tenant_id": command.get("tenant_id"),
        "device_id": command.get("device_id"),
        "command_type": command.get("command_type"),
        "status": status,
        "timestamp": int(time.time()),
        "schema_version": "1.0.0",
    }
    if dispatch_payload is not None:
        event["dispatch"] = dispatch_payload
    return event


def maybe_start_worker() -> None:
    if not KAFKA_ENABLED or not KAFKA_BROKERS.strip() or KafkaConsumer is None or KafkaProducer is None:
        return
    worker = threading.Thread(target=kafka_worker, daemon=True)
    worker.start()


def kafka_worker() -> None:
    brokers = [item.strip() for item in KAFKA_BROKERS.split(",") if item.strip()]
    if not brokers:
        return

    while True:
        consumer = None
        producer = None
        try:
            consumer = KafkaConsumer(
                KAFKA_COMMAND_TOPIC,
                bootstrap_servers=brokers,
                group_id=KAFKA_GROUP_ID,
                enable_auto_commit=True,
                auto_offset_reset="latest",
                value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            )
            producer = KafkaProducer(
                bootstrap_servers=brokers,
                value_serializer=lambda value: json.dumps(value).encode("utf-8"),
                key_serializer=lambda value: value.encode("utf-8") if value else None,
            )
            print(
                f"command-dispatcher: consuming {KAFKA_COMMAND_TOPIC} and publishing {KAFKA_LIFECYCLE_TOPIC}",
                flush=True,
            )

            for message in consumer:
                command = message.value if isinstance(message.value, dict) else {}
                METRICS["commands_consumed_total"] += 1
                dispatch_payload = build_dispatch_payload(command)
                try:
                    event = lifecycle_event(command, "sent", dispatch_payload)
                    key = command.get("command_id") or command.get("device_id") or "unknown"
                    producer.send(KAFKA_LIFECYCLE_TOPIC, key=key, value=event).get(timeout=5)
                    METRICS["commands_dispatched_total"] += 1
                    store_dispatch(event)
                except Exception:
                    METRICS["dispatch_failures_total"] += 1
        except Exception as exc:
            print(f"command-dispatcher: kafka worker error: {exc}", flush=True)
            time.sleep(5)
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass
            if producer is not None:
                try:
                    producer.close()
                except Exception:
                    pass


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "CommandDispatcher/0.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                {
                    "status": "ok",
                    "service": "command-dispatcher",
                    "configured_backends": {
                        "kafka_brokers": KAFKA_BROKERS or None,
                        "kafka_command_topic": KAFKA_COMMAND_TOPIC,
                        "kafka_lifecycle_topic": KAFKA_LIFECYCLE_TOPIC,
                        "kafka_group_id": KAFKA_GROUP_ID,
                        "mqtt_topic_template": MQTT_TOPIC_TEMPLATE,
                    },
                    "cached_dispatches": len(RECENT_DISPATCHES),
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

        if self.path == "/dispatches":
            json_response(self, RECENT_DISPATCHES)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    maybe_start_worker()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"command-dispatcher listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
