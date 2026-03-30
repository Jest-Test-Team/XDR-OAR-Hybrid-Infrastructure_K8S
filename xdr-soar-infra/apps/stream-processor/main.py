#!/usr/bin/env python3

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "8094"))
SOURCE_TOPIC = os.getenv("SOURCE_TOPIC", "telemetry.normalized")
SINK_TOPIC = os.getenv("SINK_TOPIC", "telemetry.enriched")
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1.0.0")
ALLOWED_SOURCES = {"watchdog", "agent", "sensor", "ingest_gateway", "yara", "integration", "manual"}
ALLOWED_LAYERS = {"kernel", "user", "network", "process", "file", "identity", "cloud"}
REQUIRED_FIELDS = (
    "event_id",
    "tenant_id",
    "device_id",
    "agent_id",
    "source",
    "layer",
    "category",
    "severity",
    "risk_score",
    "timestamp",
    "payload",
)


def write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_timestamp(value) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, UTC)
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).astimezone(UTC)
        except ValueError:
            if value.isdigit():
                return datetime.fromtimestamp(int(value) / 1000.0, UTC)
    return now_utc()


def parse_int(value) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(float(value))
    return 0


def parse_float(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0


def risk_level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def category_hash(category: str, layer: str) -> str:
    material = f"{category.strip()}|{layer.strip()}".encode("utf-8")
    if material == b"|":
        return ""
    return hashlib.sha256(material).hexdigest()[:16]


def generate_event_id(event: dict, event_time: datetime) -> str:
    tenant = event.get("tenant_id") or "unknown"
    device = event.get("device_id") or "unknown"
    return f"{tenant}:{device}:{int(event_time.timestamp() * 1000)}"


def normalize_event(raw: dict) -> dict:
    event_time = parse_timestamp(raw.get("timestamp"))
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    cleaned = {
        "event_id": raw.get("event_id") or "",
        "seq": parse_int(raw.get("seq")),
        "tenant_id": raw.get("tenant_id") or "",
        "device_id": raw.get("device_id") or "",
        "agent_id": raw.get("agent_id") or "",
        "watchdog_id": raw.get("watchdog_id") or "",
        "source": raw.get("source") or "",
        "layer": raw.get("layer") or "",
        "category": raw.get("category") or "",
        "severity": raw.get("severity") or "",
        "risk_score": parse_float(raw.get("risk_score")),
        "payload": payload,
        "payload_json": json.dumps(payload, separators=(",", ":"), sort_keys=True),
        "warning_metadata": raw.get("warning_metadata") or {},
        "timestamp": event_time.isoformat().replace("+00:00", "Z"),
        "category_hash": category_hash(str(raw.get("category") or ""), str(raw.get("layer") or "")),
        "risk_level": risk_level(parse_float(raw.get("risk_score"))),
        "cleaned_at": now_utc().isoformat().replace("+00:00", "Z"),
        "schema_version": raw.get("schema_version") or SCHEMA_VERSION,
    }
    if not cleaned["event_id"]:
        cleaned["event_id"] = generate_event_id(cleaned, event_time)
    return cleaned


def schema_qa(raw: dict, cleaned: dict) -> dict:
    missing_fields = []
    for field in REQUIRED_FIELDS:
        value = raw.get(field)
        if value in (None, ""):
            missing_fields.append(field)

    ingest_time = now_utc()
    event_time = parse_timestamp(cleaned.get("timestamp"))
    drift_seconds = abs((ingest_time - event_time).total_seconds())
    score = 1.0
    score -= (len(missing_fields) / len(REQUIRED_FIELDS)) * 0.5
    if drift_seconds > 300:
        score -= 0.2
    if cleaned.get("source") not in ALLOWED_SOURCES:
        score -= 0.15
    if cleaned.get("layer") not in ALLOWED_LAYERS:
        score -= 0.15
    score = max(score, 0.0)
    if score >= 0.8:
        quality_tier = "high"
    elif score >= 0.5:
        quality_tier = "medium"
    else:
        quality_tier = "low"

    return {
        "event_id": cleaned["event_id"],
        "missing_fields": missing_fields,
        "missing_rate": len(missing_fields) / len(REQUIRED_FIELDS),
        "time_drift_sec": drift_seconds,
        "time_drift_exceed": drift_seconds > 300,
        "source_ok": cleaned.get("source") in ALLOWED_SOURCES,
        "layer_ok": cleaned.get("layer") in ALLOWED_LAYERS,
        "quality_score": round(score, 4),
        "quality_tier": quality_tier,
        "ingest_time": ingest_time.isoformat().replace("+00:00", "Z"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "StreamProcessor/0.2"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            write_json(
                self,
                {
                    "status": "ok",
                    "service": "stream-processor",
                    "source_topic": SOURCE_TOPIC,
                    "sink_topic": SINK_TOPIC,
                    "schema_version": SCHEMA_VERSION,
                    "time": int(time.time()),
                },
            )
            return
        write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/normalize":
            write_json(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            raw_event = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            write_json(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        cleaned = normalize_event(raw_event)
        qa = schema_qa(raw_event, cleaned)
        write_json(
            self,
            {
                "status": "normalized",
                "source_topic": SOURCE_TOPIC,
                "sink_topic": SINK_TOPIC,
                "event": cleaned,
                "schema_qa": qa,
            },
        )


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"stream-processor listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
