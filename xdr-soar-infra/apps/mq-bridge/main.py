#!/usr/bin/env python3

import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8093"))
INPUT_TOPIC = os.getenv("INPUT_TOPIC", "telemetry.raw")
OUTPUT_TOPIC = os.getenv("OUTPUT_TOPIC", "telemetry.normalized")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "")
MQTT_BROKER_PORT = os.getenv("MQTT_BROKER_PORT", "")


def write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def build_routing_key(message: dict) -> str:
    tenant = str(message.get("tenant_id") or "*")
    device = str(message.get("device_id") or "*")
    layer = str(message.get("layer") or "*")
    category = str(message.get("category") or "*")
    return f"events.{tenant}.{device}.{layer}.{category}"


class Handler(BaseHTTPRequestHandler):
    server_version = "MQBridge/0.2"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            write_json(
                self,
                {
                    "status": "ok",
                    "service": "mq-bridge",
                    "input_topic": INPUT_TOPIC,
                    "output_topic": OUTPUT_TOPIC,
                    "configured_backends": {
                        "kafka_bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS or None,
                        "mqtt_broker": f"{MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}" if MQTT_BROKER_HOST and MQTT_BROKER_PORT else None,
                    },
                    "time": int(time.time()),
                },
            )
            return
        write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/publish":
            write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            message = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            write_json(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        write_json(
            self,
            {
                "status": "bridged",
                "input_topic": INPUT_TOPIC,
                "output_topic": OUTPUT_TOPIC,
                "routing_key": build_routing_key(message),
                "message": message,
            },
            HTTPStatus.ACCEPTED,
        )


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"mq-bridge listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
