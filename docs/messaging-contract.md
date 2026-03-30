# SOAR_K8S Messaging Contract

Date: 2026-03-30

## Purpose

This document defines the messaging contract for transport between:

- endpoint agents
- MQTT broker
- backend command dispatchers
- event ingest services
- command/result reconciliation workers

It is primarily derived from:

- `Cloud_Console_IDS-IPS/docs/MQTT_TOPIC_CONTRACT.md`
- `Cloud_Console_IDS-IPS/docs/AGENT_COMM_ARCHITECTURE.md`
- `AXIOM-Rule-SIEM-engine/docs/COMMAND_SCHEMA.md`

## Transport Roles

### MQTT

Use MQTT for:

- device-targeted commands
- updater notifications
- lightweight agent telemetry where appropriate

### AMQP

Use AMQP for:

- backend service workflows
- durable internal command/event fan-out where broker semantics matter

### Kafka

Use Kafka for:

- event streaming
- normalized telemetry
- detection signals
- incident and command lifecycle analytics

## MQTT Topics

## Device command topic

Topic:

`jobs/commands/{device_id}`

Purpose:

- deliver a command to a specific device

Payload example:

```json
{
  "command_id": "cmd-12345",
  "correlation_id": "corr-12345",
  "tenant_id": "tenant-001",
  "device_id": "device-001",
  "command_type": "update_firmware",
  "risk_level": "R4",
  "requires_presence": true,
  "approval_required": true,
  "parameters": {
    "release_id": "release-42",
    "artifact_url": "https://api.example/v1/firmware/2.3.1",
    "digest": "sha256:..."
  },
  "issued_at": "2026-03-30T10:30:00Z",
  "schema_version": "1.0.0"
}
```

## Command notification topic

Topic:

`jobs/commands/notify/{device_id}`

Purpose:

- notify a device that work is queued and should be pulled or handled immediately

Payload example:

```json
{
  "job_id": "job-12345",
  "campaign_id": "campaign-001",
  "device_id": "device-001",
  "state": "queued",
  "request_id": "req-12345",
  "issued_at": "2026-03-30T10:30:00Z",
  "schema_version": "1.0.0"
}
```

## Device-scoped topic prefix

Topic:

`devices/{device_id}/#`

Purpose:

- reserve a namespace for device-specific traffic

Recommended subtopics:

- `devices/{device_id}/status`
- `devices/{device_id}/heartbeat`
- `devices/{device_id}/ack`
- `devices/{device_id}/result`
- `devices/{device_id}/events`

## Agent Subscriptions

Each agent should subscribe to:

- `jobs/commands/notify/{device_id}`
- `jobs/commands/{device_id}`
- `devices/{device_id}/#`

## Agent Publications

Each agent should publish to:

- `devices/{device_id}/heartbeat`
- `devices/{device_id}/ack`
- `devices/{device_id}/result`
- `devices/{device_id}/events`

## ACK Payload

```json
{
  "command_id": "cmd-12345",
  "correlation_id": "corr-12345",
  "device_id": "device-001",
  "status": "acked",
  "timestamp": "2026-03-30T10:30:02Z",
  "schema_version": "1.0.0"
}
```

## Result Payload

```json
{
  "command_id": "cmd-12345",
  "correlation_id": "corr-12345",
  "device_id": "device-001",
  "status": "completed",
  "result": {
    "exit_code": 0,
    "stdout": "ok",
    "stderr": "",
    "execution_time_ms": 150
  },
  "timestamp": "2026-03-30T10:30:12Z",
  "schema_version": "1.0.0"
}
```

## Heartbeat Payload

```json
{
  "device_id": "device-001",
  "agent_id": "agent-001",
  "status": "online",
  "last_seen_at": "2026-03-30T10:30:00Z",
  "schema_version": "1.0.0"
}
```

## MQTT Delivery Rules

### QoS

- QoS 1 for commands and updater notifications
- QoS 0 for non-critical status chatter

### Retention

- do not retain high-volume telemetry messages
- retain only if there is a clear need for bootstrapping device state

### Persistence

Broker-side persistence should be enabled for:

- commands
- update notifications
- critical acknowledgements if supported by the broker flow

## Required Message Headers Or Equivalent Metadata

Every command or result message should carry:

- `tenant_id`
- `device_id`
- `correlation_id`
- `timestamp`
- `schema_version`

If broker headers are unavailable, these must exist in the JSON body.

## Internal Backend Routing

### AMQP

Recommended exchanges:

- `telemetry.events`
- `commands.issue`
- `commands.result`

Recommended routing keys:

- `events.{tenant_id}.{device_id}.{layer}.{category}`
- `cmd.{tenant_id}.{device_id}.{command_type}`
- `result.{tenant_id}.{device_id}.{command_type}`

### Kafka

Recommended topics:

- `telemetry.raw`
- `telemetry.normalized`
- `telemetry.enriched`
- `detections.signals`
- `detections.incidents`
- `commands.issue`
- `commands.lifecycle`

## Approval And Presence Semantics

Messaging must not be the source of approval truth.

Required rule:

- approval state is decided in the control plane first
- only approved commands are published to execution topics
- presence requirements must be encoded in the command envelope for auditability

## Failure Handling

Required behavior:

- duplicate ACK or result messages must be idempotent
- late results must still be recorded if `command_id` is known
- expired commands must not be executed
- failed delivery attempts must emit audit and retry metadata

## Security Requirements

1. Device-facing MQTT should use TLS.
2. Device identity should map to authenticated broker credentials or client certs.
3. Commands must be scoped by `tenant_id` and `device_id`.
4. High-risk commands must never bypass approval policy.
5. Every command publication must produce an audit event.

## Versioning

Current version:

- `1.0.0`

Compatibility rule:

- topic names are stable within a major version
- payload additions are allowed in minor versions
- routing-key changes require explicit migration planning
