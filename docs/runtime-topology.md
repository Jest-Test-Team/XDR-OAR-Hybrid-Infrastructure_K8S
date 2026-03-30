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
- `detection-engine` can now consume from Kafka and publish detection signals
- the rule engine is still placeholder-level compared to AXIOM

### 4. Control Plane

Current in-repo services:

- `firmware-api`
- static `admin-frontend`
- static `soar-dashboard`

Current maturity:

- firmware delivery exists
- incident/playbook/approval/control-plane APIs do not yet exist

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
- incident emission to a SOAR control plane
- command/result reconciliation services
- AXIOM-style multi-layer rule evaluation

## Recommended Next Step

The next meaningful runtime step is:

- upgrade `detection-engine` from threshold-style signal generation to AXIOM-style layered rules

After that:

- add MQTT or AMQP transport support to `mq-bridge`
- wire normalized output into the future rule engine
