# SOAR_K8S Command Schema

Date: 2026-03-30

## Purpose

This document defines the canonical command contract for `SOAR_K8S`.

It is primarily derived from:

- `AXIOM-Rule-SIEM-engine/docs/COMMAND_SCHEMA.md`
- `Cloud_Console_IDS-IPS/internal/playbook/dispatcher.go`
- `Cloud_Console_IDS-IPS/internal/playbook/engine.go`

This schema is used between:

- playbook/risk-policy services
- command dispatchers
- MQTT/AMQP delivery workers
- endpoint agents
- audit and reconciliation services

## Design Rules

1. Every command must be traceable back to an incident or playbook execution.
2. Every command must carry a risk classification.
3. Approval and presence requirements must be explicit in the command record, not implicit in UI logic.
4. Command delivery and command execution are separate tracked states.

## Canonical Command

```json
{
  "command_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "660e8400-e29b-41d4-a716-446655440000",
  "run_id": "93c1ff53-a930-4d96-8b67-c2524c26b778",
  "tenant_id": "tenant-001",
  "device_id": "device-abc-123",
  "incident_id": "c5465b85-c2ec-48f3-a58b-294611a6d786",
  "playbook_id": "8d3d2ab2-b9b1-4d94-8c7e-72dd55cdbd64",
  "playbook_version": "1.2.0",
  "command_type": "block.domain",
  "requires_presence": false,
  "approval_required": false,
  "risk_level": "R1",
  "payload": {
    "domain": "malicious.example.com",
    "ttl": 3600
  },
  "expires_at": "2026-03-30T11:30:00Z",
  "rollback_plan": {
    "rollback_id": "770e8400-e29b-41d4-a716-446655440000",
    "action": "unblock.domain"
  },
  "execution_policy": {
    "timeout_seconds": 30,
    "retry": 3,
    "max_attempts": 3
  },
  "issued_at": "2026-03-30T10:30:00Z",
  "schema_version": "1.0.0"
}
```

## Required Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `command_id` | string | yes | unique command identifier |
| `correlation_id` | string | yes | links incident, playbook, delivery, result |
| `tenant_id` | string | yes | tenant boundary |
| `device_id` | string | yes | target device |
| `command_type` | string | yes | action verb |
| `requires_presence` | boolean | yes | operator-presence requirement |
| `approval_required` | boolean | yes | workflow-gating requirement |
| `risk_level` | string | yes | `R0-R4` |
| `payload` | object | yes | action parameters |
| `issued_at` | string | yes | issue timestamp |
| `schema_version` | string | yes | contract version |

## Optional But Recommended Fields

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | execution batch or workflow run |
| `incident_id` | string | owning incident |
| `playbook_id` | string | generating playbook |
| `playbook_version` | string | playbook version |
| `expires_at` | string | hard expiry |
| `rollback_plan` | object | rollback metadata |
| `execution_policy` | object | timeout/retry policy |

## Risk Levels

### `R0`

Read-only or evidence collection.

Examples:

- `collect.telemetry`
- `collect.hashes`
- `snapshot.netstat`

### `R1`

Low-impact, reversible action.

Examples:

- `block.domain`
- `kill.process`
- `quarantine.file`

### `R2`

Controlled but broader operational impact.

Examples:

- `block.ip`
- `disable.persistence`

### `R3`

Operationally disruptive action requiring presence.

Examples:

- `isolate.host`
- `stop.service`
- `disable.user_session`

### `R4`

High-destruction or hard-to-reverse action requiring strong controls.

Examples:

- `wipe`
- `uninstall`
- `rotate.identity`
- `delete.evidence`
- `firmware.flash`

## Control Semantics

### `requires_presence`

Indicates live operator presence is required before execution.

Typical default:

- `true` for `R3-R4`
- `false` for `R0-R2`

### `approval_required`

Indicates workflow approval is required before dispatch.

Typical default:

- `false` for `R0-R1`
- conditional for `R2`
- `true` for `R3-R4`

## Example Command Types

### Block domain

```json
{
  "command_type": "block.domain",
  "payload": {
    "domain": "malicious.example.com",
    "ttl": 3600
  }
}
```

### Isolate host

```json
{
  "command_type": "isolate.host",
  "requires_presence": true,
  "approval_required": true,
  "payload": {
    "network_quarantine": true,
    "allow_internal": false
  }
}
```

### Firmware update

```json
{
  "command_type": "update_firmware",
  "requires_presence": true,
  "approval_required": true,
  "risk_level": "R4",
  "payload": {
    "release_id": "release-123",
    "artifact_url": "https://api.example/v1/firmware/2.3.1",
    "digest": "sha256:..."
  }
}
```

## Command Status Model

Command state must be tracked outside the command envelope itself.

Recommended statuses:

- `pending_approval`
- `approved`
- `rejected`
- `queued`
- `sent`
- `acked`
- `completed`
- `failed`
- `expired`
- `rolled_back`

## Reconciliation Records

The platform should persist:

- command record
- delivery attempt record
- agent acknowledgement record
- execution result record
- approval request/decision record
- audit log entry for every state transition

## Delivery Model

Internal delivery may use:

- MQTT for device-facing commands
- AMQP for backend workflow
- Kafka for analytics/eventing around command lifecycle

Every delivery message must include:

- `command_id`
- `correlation_id`
- `tenant_id`
- `device_id`
- `command_type`

## Versioning

Current version:

- `1.0.0`

Compatibility rule:

- additive fields are allowed in minor versions
- changes to required control semantics require a major version bump

## Minimal Validation Checklist

Every producer should enforce:

1. `command_id` present
2. `correlation_id` present
3. `tenant_id` and `device_id` present
4. `command_type` present
5. `risk_level` valid
6. `requires_presence` and `approval_required` explicitly set
7. `payload` object
8. `issued_at` valid UTC timestamp
9. `schema_version` present
