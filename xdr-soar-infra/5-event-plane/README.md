# Event Plane

This manifest group scaffolds the Phase 1 event plane for `SOAR_K8S`.

Planned responsibilities:

- HTTP ingest entrypoint
- broker-to-bus bridge
- stream normalization
- Kafka topic bootstrap

Current implementation status:

- `ingest-gateway`: partially implemented HTTP ingest contract with identity fallback, event validation, and routing-key generation
- `mq-bridge`: partial bridge stub with routing-key mapping
- `stream-processor`: partially implemented normalization and schema-QA behavior derived from AXIOM concepts

These services are still not connected to real MQTT/AMQP/Kafka clients yet.

Initial placeholder services in this directory exist to establish:

- repo layout
- deployment order
- service names
- environment contract

The implementation target is the richer ingest and stream-processing model documented in:

- `SOAR_K8S/docs/event-schema.md`
- `SOAR_K8S/docs/messaging-contract.md`
- `SOAR_K8S/docs/2026-03-30-soar-k8s-expansion-plan.md`
