# SOAR_K8S Runtime Topology

Date: 2026-03-30

## Purpose

This document describes the intended runtime topology for the current `SOAR_K8S` implementation, with emphasis on the event plane that is being expanded from AXIOM and Cloud Console patterns.

## Current Runtime Layers

### 1. Endpoint Layer

- Windows/macOS agents
- watchdog processes
- updater workflow

Primary edge transports:

- MQTT TLS for device-facing notifications and commands
- HTTPS for firmware retrieval and ingest fallback

### 2. Event Plane

Current in-repo services:

- `ingest-gateway`
- `mq-bridge`
- `stream-processor`

Current maturity:

- contracts and deployment wiring exist
- `ingest-gateway` has a Kafka producer path
- `mq-bridge` has an HTTP-to-Kafka bridge path
- `stream-processor` has a Kafka consume/publish path
- partial normalization and schema-QA logic exists
- real MQTT/AMQP client integration is not yet implemented

### 3. Detection Plane

Current in-repo services:

- `detection-engine`
- `ml-triton-server`
- `ml-retraining`
- `yara-scanner`

Current maturity:

- ML and scanner scaffolding exists
- `detection-engine` can now consume from Kafka and publish detection signals and incident records
- the rule engine is still placeholder-level compared to AXIOM

### 4. Control Plane

Current in-repo services:

- `firmware-api`
- `soar-api`
- `command-dispatcher`
- `command-reconciler`
- static `admin-frontend`
- static `soar-dashboard`

Current maturity:

- firmware delivery exists
- `soar-api` can now consume `detections.incidents` and expose incident reads
- `soar-api` now exposes minimal playbook, approval, and command APIs
- `soar-api` now performs basic incident-to-playbook matching and approval/command state transitions
- `soar-api` now exposes audit records and optional persistence targets for core control-plane objects
- `command-dispatcher` now consumes `commands.issue` and emits `commands.lifecycle`
- `command-reconciler` now consumes `commands.lifecycle` and tracks command state transitions
- `soar-api` now also consumes `commands.lifecycle` so API-visible command records reflect dispatch, ACK, completion, and failure states
- playbook/approval/command workflows are still placeholder-level overall

## Target Event Flow

Recommended target path:

1. endpoint emits raw event
2. `ingest-gateway` accepts and validates envelope
3. `mq-bridge` bridges broker-side transport into Kafka-facing topics
4. `stream-processor` normalizes event shape and computes QA metadata
5. normalized events are written to:
   - Kafka event topics
   - InfluxDB telemetry storage
   - downstream detection/rule services
6. `detection-engine` consumes enriched events and publishes detection signals
7. high-risk signals are promoted into incident records on `detections.incidents`
8. `soar-api` consumes `detections.incidents` and exposes `/api/v1/incidents`
9. `soar-api` maintains minimal `/api/v1/playbooks`, `/api/v1/commands`, and `/api/v1/approvals` resources
10. `soar-api` performs basic playbook matching, approval decisions, and command status transitions
11. `soar-api` records audit events and can persist incidents/playbooks/commands/approvals/audit logs via Supabase REST
12. `command-dispatcher` consumes approved/queued commands and emits lifecycle records for dispatch
13. `command-reconciler` consumes lifecycle events and ingests ACK/result-style updates into reconciled command state
14. `soar-api` consumes `commands.lifecycle` and updates operator-facing command records

## Current Topic Model

### Kafka topics

- `telemetry.raw`
- `telemetry.normalized`
- `telemetry.enriched`
- `detections.signals`
- `detections.incidents`

### MQTT topics

- `jobs/commands/{device_id}`
- `jobs/commands/notify/{device_id}`
- `devices/{device_id}/heartbeat`
- `devices/{device_id}/ack`
- `devices/{device_id}/result`
- `devices/{device_id}/events`

### AMQP routing keys

- `events.{tenant_id}.{device_id}.{layer}.{category}`
- `cmd.{tenant_id}.{device_id}.{command_type}`
- `result.{tenant_id}.{device_id}.{command_type}`

## Current Service Configuration Surface

Event-plane runtime configuration is now centralized in:

- `xdr-soar-infra/5-event-plane/00-configmap.yaml`

It currently defines:

- schema version
- Kafka bootstrap address
- MQTT broker host/ports
- ingest path
- event-plane topic names
- stream-processor consumer group

This is a preparation step for real client integration and keeps the deployment contract stable while implementation catches up.

## Current Gaps

The following are still not implemented:

- real MQTT or AMQP client connectivity in the event-plane services
- durable command ACK/result persistence in the control plane data model
- AXIOM-style multi-layer rule evaluation
- real playbook execution and durable workflow orchestration

## Recommended Next Step

The next meaningful runtime step is:

- move command lifecycle reconciliation from cache-level updates to durable relational persistence and queryable workflow state

After that:

- replace placeholder playbook/approval/command state handling with real workflow execution and dispatch
- upgrade `detection-engine` from threshold-style signal generation to AXIOM-style layered rules
- add MQTT or AMQP transport support to `mq-bridge`
- wire normalized output into the future rule engine

## Progress Percentage

Estimated progress by phase:

- Phase 0 Contracts and topology: `100%`
- Phase 1 Event plane transport and normalization: `85%`
- Phase 2 Detection and incident generation: `45%`
- Phase 3 SOAR control plane: `74%`
- Phase 4 UI and external integrations: `10%`

Estimated overall repo expansion progress:

- `73%`
