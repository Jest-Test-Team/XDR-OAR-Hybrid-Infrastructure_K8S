#!/usr/bin/env python3

import json
import os
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY", "")
RISK_THRESHOLD = int(os.getenv("RISK_THRESHOLD", "85"))

METRICS = {
    "telemetry_events_total": 0,
    "alerts_published_total": 0,
    "alert_publish_failures_total": 0,
}


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def publish_alert(alert: dict) -> bool:
    if not SUPABASE_REST_URL:
        return False

    request = urllib.request.Request(
        SUPABASE_REST_URL,
        data=json.dumps(alert).encode("utf-8"),
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


def render_metrics() -> str:
    return "\n".join(
        [
            "# HELP detection_engine_telemetry_events_total Number of processed telemetry events.",
            "# TYPE detection_engine_telemetry_events_total counter",
            f"detection_engine_telemetry_events_total {METRICS['telemetry_events_total']}",
            "# HELP detection_engine_alerts_published_total Number of alerts sent to Supabase.",
            "# TYPE detection_engine_alerts_published_total counter",
            f"detection_engine_alerts_published_total {METRICS['alerts_published_total']}",
            "# HELP detection_engine_alert_publish_failures_total Number of failed alert publications.",
            "# TYPE detection_engine_alert_publish_failures_total counter",
            f"detection_engine_alert_publish_failures_total {METRICS['alert_publish_failures_total']}",
        ]
    ) + "\n"


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "DetectionEngine/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                {
                    "status": "ok",
                    "time": int(time.time()),
                    "supabase_rest_url": SUPABASE_REST_URL or None,
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

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/telemetry":
            json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(content_length)
        try:
            telemetry = json.loads(payload or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        METRICS["telemetry_events_total"] += 1
        host = telemetry.get("hostname", "unknown")
        severity = int(telemetry.get("severity", 0))
        indicators = telemetry.get("indicators", [])
        risk_score = min(100, severity * 10 + len(indicators) * 8 + len(json.dumps(telemetry)) % 25)

        response = {
            "hostname": host,
            "risk_score": risk_score,
            "alert_emitted": False,
        }

        if risk_score >= RISK_THRESHOLD:
            alert = {
                "hostname": host,
                "risk_score": risk_score,
                "indicators": indicators,
                "generated_at": int(time.time()),
            }
            if publish_alert(alert):
                METRICS["alerts_published_total"] += 1
                response["alert_emitted"] = True
            else:
                METRICS["alert_publish_failures_total"] += 1

        json_response(self, response)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"detection-engine listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
