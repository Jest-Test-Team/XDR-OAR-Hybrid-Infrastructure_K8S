# SOAR_K8S Event Schema

Date: 2026-03-30

## Purpose

This document defines the canonical event contract for `SOAR_K8S`.

It is primarily derived from:

- `AXIOM-Rule-SIEM-engine/docs/EVENT_SCHEMA.md`
- `Cloud_Console_IDS-IPS/docs/EVENT_PIPELINE_INTEGRATION.md`

This schema is the contract between:

- endpoint agents and ingest services
- MQTT/HTTP/broker transport and Kafka
- stream normalization and rule engines
- rule engines and incident/playbook services

## Design Rules

1. Every event must be uniquely identifiable.
2. Every event must be attributable to a tenant and device.
3. Every event must be routable through broker, Kafka, and storage without re-shaping the payload each time.
4. The normalized event is the only format consumed by detection, correlation, and SOAR services.

## Canonical Event

```json
{
  "event_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "seq": 12345,
  "tenant_id": "tenant-001",
  "device_id": "device-abc-123",
  "agent_id": "agent-xyz-789",
  "source": "watchdog",
  "layer": "network",
  "category": "dns",
  "severity": "high",
  "risk_score": 82.5,
  "confidence": 0.94,
  "correlation_id": "1f4c8a94-5f7c-4d19-8b19-487f46074125",
  "payload": {
    "query": "malicious.example",
    "response_code": "NXDOMAIN",
    "resolver": "8.8.8.8"
  },
  "labels": {
    "site": "lab-a",
    "os": "windows"
  },
  "timestamp": "2026-03-30T10:30:00Z",
  "received_at": "2026-03-30T10:30:01Z",
  "schema_version": "1.0.0"
}
```

## Required Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `event_id` | string | yes | globally unique ULID/UUIDv7 preferred |
| `seq` | integer | yes | monotonic per `device_id` |
| `tenant_id` | string | yes | tenant boundary key |
| `device_id` | string | yes | endpoint/device identity |
| `agent_id` | string | yes | agent identity |
| `source` | string | yes | producer source |
| `layer` | string | yes | detection layer |
| `category` | string | yes | event family |
| `severity` | string | yes | `low`, `medium`, `high`, `critical` |
| `risk_score` | number | yes | `0-100` |
| `payload` | object | yes | raw event details |
| `timestamp` | string | yes | event time, ISO 8601 UTC |
| `schema_version` | string | yes | contract version |

## Optional But Recommended Fields

| Field | Type | Notes |
|---|---|---|
| `confidence` | number | `0-1` model/rule confidence |
| `correlation_id` | string | upstream trace/correlation linkage |
| `labels` | object | stable routing or indexing labels |
| `received_at` | string | ingest timestamp |

## Enumerations

### `source`

- `watchdog`
- `agent`
- `sensor`
- `ingest_gateway`
- `yara`
- `integration`
- `manual`

### `layer`

- `kernel`
- `user`
- `network`
- `process`
- `file`
- `identity`
- `cloud`

### `category`

- `network`
- `dns`
- `process`
- `file`
- `registry`
- `malware_execution`
- `lateral_movement`
- `policy_violation`
- `firmware`
- `auth`
- `cloud_alert`

## Payload Guidance

`payload` is source-specific and can vary by category, but the envelope must remain stable.

Examples:

### Network event

```json
{
  "src_ip": "192.168.1.100",
  "dst_ip": "10.0.0.1",
  "dst_port": 443,
  "protocol": "TCP",
  "bytes_sent": 1024,
  "bytes_recv": 2048,
  "latency_ms": 45
}
```

### Process event

```json
{
  "pid": 1234,
  "ppid": 567,
  "name": "malware.exe",
  "path": "C:\\Windows\\Temp\\malware.exe",
  "command_line": "malware.exe --stealth",
  "hash_sha256": "def456..."
}
```

### File scan event

```json
{
  "artifact_id": "gridfs:sample-123",
  "filename": "dropper.exe",
  "scan_engine": "yara",
  "matches": ["SuspiciousPackedBinary", "CredentialDumping"]
}
```

## Event Lifecycle

### 1. Raw ingest

The endpoint or external integration sends a raw event over:

- MQTT
- HTTPS
- AMQP
- integration worker callback

### 2. Normalization

A stream or ingest processor converts the raw event to the canonical event envelope.

### 3. Validation

Rejected conditions:

- missing `event_id`
- missing tenant/device identity
- invalid `severity`
- `risk_score` outside `0-100`
- non-object `payload`

### 4. Routing

Validated events are forwarded to:

- Kafka normalized topic
- InfluxDB telemetry storage
- rule engine consumers
- optional long-term archive

## Deduplication And Ordering

Primary dedupe key:

- `(device_id, event_id)`

Ordering key:

- `seq` within a `device_id`

Required behavior:

- repeated `(device_id, event_id)` must be treated as duplicates
- `seq` gaps should be observable
- late events are allowed but must retain original `timestamp`

## Kafka Mapping

Recommended topics:

- `telemetry.raw`
- `telemetry.normalized`
- `telemetry.enriched`
- `detections.signals`
- `detections.incidents`

Recommended partition key:

- `tenant_id:device_id`

## InfluxDB Mapping

Measurement:

- `telemetry_events`

Tags:

- `tenant_id`
- `device_id`
- `agent_id`
- `source`
- `layer`
- `category`
- `severity`

Fields:

- `risk_score`
- `confidence`
- `event_count`
- `payload_hash`
- `bytes_in`
- `bytes_out`
- `latency_ms`

## Rule Engine Expectations

Detection and SOAR services may assume:

- envelope fields are stable
- payload is already normalized enough for rule matching
- `risk_score` exists even if upstream logic is simple
- `correlation_id` may be absent and can be generated downstream

## Versioning

Current version:

- `1.0.0`

Compatibility rule:

- additive fields are allowed in minor versions
- removing or changing required field meaning requires a major version bump

## Minimal Validation Checklist

Every producer or normalizer should enforce:

1. `event_id` present
2. `tenant_id`, `device_id`, `agent_id` present
3. `source`, `layer`, `category`, `severity` present
4. `risk_score` numeric and bounded
5. `payload` object
6. `timestamp` valid UTC timestamp
7. `schema_version` present
