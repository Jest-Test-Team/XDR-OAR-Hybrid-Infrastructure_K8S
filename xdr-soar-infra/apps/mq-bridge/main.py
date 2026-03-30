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


def write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "MQBridge/0.1"

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
                    "time": int(time.time()),
                },
            )
            return
        write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"mq-bridge listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
