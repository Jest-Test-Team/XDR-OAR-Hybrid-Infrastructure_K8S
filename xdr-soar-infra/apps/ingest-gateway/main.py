#!/usr/bin/env python3

import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8082"))
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1.0.0")


def write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "IngestGateway/0.1"

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
            write_json(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        write_json(
            self,
            {
                "status": "accepted",
                "service": "ingest-gateway",
                "received_at": int(time.time()),
                "schema_version": SCHEMA_VERSION,
                "event_id": payload.get("event_id"),
            },
            HTTPStatus.ACCEPTED,
        )


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ingest-gateway listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
