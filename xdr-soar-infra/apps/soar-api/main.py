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
from urllib.parse import urlparse

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
PLAYBOOKS: list[dict] = [
    {
        "playbook_id": "pb-auto-block-domain",
        "name": "Auto Block Domain",
        "version": "0.1.0",
        "enabled": True,
        "match_category": "dns",
        "risk_level": "R1",
        "actions": [{"type": "block.domain", "ttl": 3600}],
    },
    {
        "playbook_id": "pb-isolate-host-review",
        "name": "Isolate Host With Approval",
        "version": "0.1.0",
        "enabled": True,
        "match_category": "malware_execution",
        "risk_level": "R3",
        "actions": [{"type": "isolate.host"}],
    },
]
APPROVALS: list[dict] = []
COMMANDS: list[dict] = []
MAX_INCIDENTS = 500
METRICS = {
    "incidents_consumed_total": 0,
    "incidents_persisted_total": 0,
    "incident_persist_failures_total": 0,
    "commands_created_total": 0,
    "approvals_created_total": 0,
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
            "# HELP soar_api_commands_created_total Number of command records created.",
            "# TYPE soar_api_commands_created_total counter",
            f"soar_api_commands_created_total {METRICS['commands_created_total']}",
            "# HELP soar_api_approvals_created_total Number of approval records created.",
            "# TYPE soar_api_approvals_created_total counter",
            f"soar_api_approvals_created_total {METRICS['approvals_created_total']}",
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


def store_limited(collection: list[dict], item: dict) -> None:
    collection.insert(0, item)
    del collection[MAX_INCIDENTS:]


def create_command_from_incident(incident: dict) -> dict | None:
    category = incident.get("category")
    device_id = incident.get("device_id")
    tenant_id = incident.get("tenant_id")
    incident_id = incident.get("incident_id")
    risk_score = float(incident.get("risk_score") or 0)

    if category == "dns":
        command = {
            "command_id": str(uuid.uuid4()),
            "correlation_id": incident.get("correlation_id") or incident_id or str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "device_id": device_id,
            "incident_id": incident_id,
            "playbook_id": "pb-auto-block-domain",
            "playbook_version": "0.1.0",
            "command_type": "block.domain",
            "requires_presence": False,
            "approval_required": False,
            "risk_level": "R1",
            "payload": {
                "domain": incident.get("signal", {}).get("payload", {}).get("query", "unknown"),
                "ttl": 3600,
            },
            "issued_at": int(time.time()),
            "status": "queued",
            "schema_version": "1.0.0",
        }
        return command

    if risk_score >= 85:
        command = {
            "command_id": str(uuid.uuid4()),
            "correlation_id": incident.get("correlation_id") or incident_id or str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "device_id": device_id,
            "incident_id": incident_id,
            "playbook_id": "pb-isolate-host-review",
            "playbook_version": "0.1.0",
            "command_type": "isolate.host",
            "requires_presence": True,
            "approval_required": True,
            "risk_level": "R3",
            "payload": {
                "network_quarantine": True,
                "allow_internal": False,
            },
            "issued_at": int(time.time()),
            "status": "pending_approval",
            "schema_version": "1.0.0",
        }
        return command

    return None


def maybe_create_followup_records(incident: dict) -> None:
    command = create_command_from_incident(incident)
    if not command:
        return

    store_limited(COMMANDS, command)
    METRICS["commands_created_total"] += 1

    if command["approval_required"]:
        approval = {
            "approval_id": str(uuid.uuid4()),
            "command_id": command["command_id"],
            "incident_id": incident.get("incident_id"),
            "risk_level": command["risk_level"],
            "status": "pending",
            "requested_at": int(time.time()),
            "schema_version": "1.0.0",
        }
        store_limited(APPROVALS, approval)
        METRICS["approvals_created_total"] += 1


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
                maybe_create_followup_records(incident)
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
        parsed = urlparse(self.path)

        if parsed.path in {"/health", "/api/v1/health"}:
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
                    "cached_playbooks": len(PLAYBOOKS),
                    "cached_commands": len(COMMANDS),
                    "cached_approvals": len(APPROVALS),
                    "time": int(time.time()),
                },
            )
            return

        if parsed.path == "/metrics":
            body = render_metrics().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/v1/incidents":
            json_response(self, INCIDENTS)
            return

        if parsed.path == "/api/v1/playbooks":
            json_response(self, PLAYBOOKS)
            return

        if parsed.path == "/api/v1/commands":
            json_response(self, COMMANDS)
            return

        if parsed.path == "/api/v1/approvals":
            json_response(self, APPROVALS)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "invalid json"}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/v1/playbooks":
            playbook = {
                "playbook_id": payload.get("playbook_id") or str(uuid.uuid4()),
                "name": payload.get("name") or "Unnamed Playbook",
                "version": payload.get("version") or "0.1.0",
                "enabled": bool(payload.get("enabled", True)),
                "match_category": payload.get("match_category"),
                "risk_level": payload.get("risk_level", "R1"),
                "actions": payload.get("actions", []),
            }
            store_limited(PLAYBOOKS, playbook)
            json_response(self, playbook, HTTPStatus.CREATED)
            return

        if parsed.path == "/api/v1/commands":
            command = {
                "command_id": payload.get("command_id") or str(uuid.uuid4()),
                "correlation_id": payload.get("correlation_id") or str(uuid.uuid4()),
                "tenant_id": payload.get("tenant_id"),
                "device_id": payload.get("device_id"),
                "incident_id": payload.get("incident_id"),
                "playbook_id": payload.get("playbook_id"),
                "playbook_version": payload.get("playbook_version", "0.1.0"),
                "command_type": payload.get("command_type"),
                "requires_presence": bool(payload.get("requires_presence", False)),
                "approval_required": bool(payload.get("approval_required", False)),
                "risk_level": payload.get("risk_level", "R1"),
                "payload": payload.get("payload", {}),
                "issued_at": payload.get("issued_at") or int(time.time()),
                "status": payload.get("status", "queued"),
                "schema_version": "1.0.0",
            }
            store_limited(COMMANDS, command)
            METRICS["commands_created_total"] += 1
            json_response(self, command, HTTPStatus.CREATED)
            return

        if parsed.path == "/api/v1/approvals":
            approval = {
                "approval_id": payload.get("approval_id") or str(uuid.uuid4()),
                "command_id": payload.get("command_id"),
                "incident_id": payload.get("incident_id"),
                "risk_level": payload.get("risk_level", "R1"),
                "status": payload.get("status", "pending"),
                "requested_at": payload.get("requested_at") or int(time.time()),
                "schema_version": "1.0.0",
            }
            store_limited(APPROVALS, approval)
            METRICS["approvals_created_total"] += 1
            json_response(self, approval, HTTPStatus.CREATED)
            return

        json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)


def main() -> None:
    maybe_start_consumer()
    server = ThreadingHTTPServer((HOST, PORT), RequestHandler)
    print(f"soar-api listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
