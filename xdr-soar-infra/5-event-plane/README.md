# Event Plane

This manifest group scaffolds the Phase 1 event plane for `SOAR_K8S`.

Planned responsibilities:

- HTTP ingest entrypoint
- broker-to-bus bridge
- stream normalization
- Kafka topic bootstrap

Initial placeholder services in this directory are intentionally thin. They exist to establish:

- repo layout
- deployment order
- service names
- environment contract

The implementation target is the richer ingest and stream-processing model documented in:

- `SOAR_K8S/docs/event-schema.md`
- `SOAR_K8S/docs/messaging-contract.md`
- `SOAR_K8S/docs/2026-03-30-soar-k8s-expansion-plan.md`
