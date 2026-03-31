#!/usr/bin/env python3

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from kafka import KafkaConsumer, KafkaProducer
except ImportError:  # pragma: no cover - dependency availability is environment-specific
    KafkaConsumer = None
    KafkaProducer = None


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8080"))
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL", "").rstrip("/")
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY", "")
RISK_THRESHOLD = int(os.getenv("RISK_THRESHOLD", "85"))
KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "")
KAFKA_SOURCE_TOPIC = os.getenv("KAFKA_SOURCE_TOPIC", "telemetry.enriched")
KAFKA_SIGNAL_TOPIC = os.getenv("KAFKA_SIGNAL_TOPIC", "detections.signals")
KAFKA_INCIDENT_TOPIC = os.getenv("KAFKA_INCIDENT_TOPIC", "detections.incidents")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "detection-engine")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

METRICS = {
    "telemetry_events_total": 0,
    "alerts_published_total": 0,
    "alert_publish_failures_total": 0,
    "kafka_consumed_total": 0,
    "signals_published_total": 0,
    "signal_publish_failures_total": 0,
    "incidents_published_total": 0,
    "incident_publish_failures_total": 0,
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


def evaluate_detection(telemetry: dict) -> dict:
    hostname = telemetry.get("hostname") or telemetry.get("device_id") or "unknown"
    severity_value = telemetry.get("severity", 0)
    if isinstance(severity_value, str):
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        severity = severity_map.get(severity_value.lower(), 0)
    else:
        try:
            severity = int(severity_value)
        except (TypeError, ValueError):
            severity = 0

    indicators = telemetry.get("indicators", [])
    if not isinstance(indicators, list):
        indicators = []

    risk_score = telemetry.get("risk_score")
    if risk_score is None:
        risk_score = min(100, severity * 10 + len(indicators) * 8 + len(json.dumps(telemetry)) % 25)
    try:
        risk_score = float(risk_score)
    except (TypeError, ValueError):
        risk_score = 0.0

    signal = {
        "event_id": telemetry.get("event_id"),
        "tenant_id": telemetry.get("tenant_id"),
        "device_id": telemetry.get("device_id"),
        "hostname": hostname,
        "risk_score": risk_score,
        "severity": telemetry.get("severity", "medium"),
        "layer": telemetry.get("layer"),
        "category": telemetry.get("category"),
        "indicators": indicators,
        "generated_at": int(time.time()),
        "source": "detection-engine",
    }

    return {
        "hostname": hostname,
        "risk_score": risk_score,
        "alert_emitted": False,
        "signal": signal,
    }


def build_incident(result: dict) -> dict:
    signal = result["signal"]
    return {
        "incident_id": str(uuid.uuid4()),
        "correlation_id": signal.get("event_id") or str(uuid.uuid4()),
        "tenant_id": signal.get("tenant_id"),
        "device_id": signal.get("device_id"),
        "title": f"{signal.get('category') or 'security'} detection on {signal.get('hostname') or 'unknown'}",
        "summary": "Auto-generated incident from detection-engine threshold policy.",
        "status": "open",
        "severity": signal.get("severity", "medium"),
        "risk_score": signal.get("risk_score", 0),
        "layer": signal.get("layer"),
        "category": signal.get("category"),
        "source": "detection-engine",
        "signal": signal,
        "created_at": int(time.time()),
        "schema_version": "1.0.0",
    }


def maybe_publish_alert(result: dict) -> dict:
    if result["risk_score"] >= RISK_THRESHOLD:
        if publish_alert(result["signal"]):
            METRICS["alerts_published_total"] += 1
            result["alert_emitted"] = True
        else:
            METRICS["alert_publish_failures_total"] += 1
    return result


def maybe_start_kafka_worker() -> None:
    if not KAFKA_ENABLED or not KAFKA_BROKERS.strip():
        return
    if KafkaConsumer is None or KafkaProducer is None:
        print("detection-engine: kafka-python not installed; Kafka worker disabled", flush=True)
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
                KAFKA_SOURCE_TOPIC,
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
                (
                    f"detection-engine: consuming from {KAFKA_SOURCE_TOPIC} and publishing to "
                    f"{KAFKA_SIGNAL_TOPIC} / {KAFKA_INCIDENT_TOPIC}"
                ),
                flush=True,
            )

            for message in consumer:
                payload = message.value
                if isinstance(payload, dict) and "event" in payload and isinstance(payload["event"], dict):
                    telemetry = payload["event"]
                else:
                    telemetry = payload if isinstance(payload, dict) else {}

                METRICS["kafka_consumed_total"] += 1
                METRICS["telemetry_events_total"] += 1
                result = maybe_publish_alert(evaluate_detection(telemetry))
                key = result["signal"].get("event_id") or telemetry.get("device_id") or "unknown"

                try:
                    producer.send(KAFKA_SIGNAL_TOPIC, key=key, value=result["signal"]).get(timeout=5)
                    METRICS["signals_published_total"] += 1
                except Exception:
                    METRICS["signal_publish_failures_total"] += 1

                if result["risk_score"] >= RISK_THRESHOLD:
                    incident = build_incident(result)
                    try:
                        producer.send(KAFKA_INCIDENT_TOPIC, key=incident["incident_id"], value=incident).get(timeout=5)
                        METRICS["incidents_published_total"] += 1
                    except Exception:
                        METRICS["incident_publish_failures_total"] += 1
        except Exception as exc:
            print(f"detection-engine: kafka worker error: {exc}", flush=True)
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
            "# HELP detection_engine_kafka_consumed_total Number of Kafka messages consumed.",
            "# TYPE detection_engine_kafka_consumed_total counter",
            f"detection_engine_kafka_consumed_total {METRICS['kafka_consumed_total']}",
            "# HELP detection_engine_signals_published_total Number of detection signals published.",
            "# TYPE detection_engine_signals_published_total counter",
            f"detection_engine_signals_published_total {METRICS['signals_published_total']}",
            "# HELP detection_engine_signal_publish_failures_total Number of failed signal publications.",
            "# TYPE detection_engine_signal_publish_failures_total counter",
            f"detection_engine_signal_publish_failures_total {METRICS['signal_publish_failures_total']}",
            "# HELP detection_engine_incidents_published_total Number of incidents published.",
            "# TYPE detection_engine_incidents_published_total counter",
            f"detection_engine_incidents_published_total {METRICS['incidents_published_total']}",
            "# HELP detection_engine_incident_publish_failures_total Number of failed incident publications.",
            "# TYPE detection_engine_incident_publish_failures_total counter",
            f"detection_engine_incident_publish_failures_total {METRICS['incident_publish_failures_total']}",
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
                    "configured_backends": {
                        "kafka_brokers": KAFKA_BROKERS or None,
                        "kafka_source_topic": KAFKA_SOURCE_TOPIC,
                        "kafka_signal_topic": KAFKA_SIGNAL_TOPIC,
                        "kafka_incident_topic": KAFKA_INCIDENT_TOPIC,
                        "kafka_group_id": KAFKA_GROUP_ID,
                        "kafka_enabled": KAFKA_ENABLED,
                    },
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
        json_response(self, maybe_publish_alert(evaluate_detection(telemetry)))


def main() -> None:
    maybe_start_kafka_worker()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"detection-engine listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
