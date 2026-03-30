# Event Plane

This manifest group scaffolds the Phase 1 event plane for `SOAR_K8S`.

Planned responsibilities:

- HTTP ingest entrypoint
- broker-to-bus bridge
- stream normalization
- Kafka topic bootstrap

Current implementation status:

- `ingest-gateway`: Go service with actual Kafka publish path, identity fallback, event validation, and routing-key generation
- `mq-bridge`: partial bridge stub with routing-key mapping
- `stream-processor`: Go service with Kafka consume/publish flow plus AXIOM-style normalization and schema-QA behavior

Current transport maturity:

- Kafka publish path exists in `ingest-gateway`
- Kafka consume/publish path exists in `stream-processor`
- `mq-bridge` still does not have a real transport client
- AMQP and MQTT integration is still pending

Initial placeholder services in this directory exist to establish:

- repo layout
- deployment order
- service names
- environment contract

The implementation target is the richer ingest and stream-processing model documented in:

- `SOAR_K8S/docs/event-schema.md`
- `SOAR_K8S/docs/messaging-contract.md`
- `SOAR_K8S/docs/2026-03-30-soar-k8s-expansion-plan.md`
