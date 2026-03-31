#!/usr/bin/env python3

import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "9000"))
SIGNATURE_PATH = Path(os.getenv("SIGNATURE_PATH", "/app/signatures.json"))
METRICS = {
    "scan_requests_total": 0,
    "signature_matches_total": 0,
}


def load_signatures() -> list[dict]:
    return json.loads(SIGNATURE_PATH.read_text(encoding="utf-8"))


SIGNATURES = load_signatures()


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def render_metrics() -> str:
    return "\n".join(
        [
            "# HELP yara_scanner_scan_requests_total Number of received scan requests.",
            "# TYPE yara_scanner_scan_requests_total counter",
            f"yara_scanner_scan_requests_total {METRICS['scan_requests_total']}",
            "# HELP yara_scanner_signature_matches_total Number of signature matches emitted.",
            "# TYPE yara_scanner_signature_matches_total counter",
            f"yara_scanner_signature_matches_total {METRICS['signature_matches_total']}",
        ]
    ) + "\n"


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "YaraScanner/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(self, {"status": "ok", "loaded_signatures": len(SIGNATURES)})
            return
        if self.path == "/metrics":
            body = render_metrics().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/scan":
            json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(content_length)
        try:
            request = json.loads(payload or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        content = request.get("content", "")
        METRICS["scan_requests_total"] += 1
        matches = []

        for signature in SIGNATURES:
            if re.search(signature["pattern"], content, flags=re.IGNORECASE):
                matches.append(signature["name"])

        METRICS["signature_matches_total"] += len(matches)
        json_response(self, {"matches": matches, "matched": bool(matches)})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"yara-scanner listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
