# SOAR_K8S Expansion Plan

Date: 2026-03-30

## Goal

Expand `SOAR_K8S` by absorbing the mature SIEM/event-processing capabilities from `AXIOM-Rule-SIEM-engine` and the mature SOAR/console/integration capabilities from `Cloud_Console_IDS-IPS`, while preserving `SOAR_K8S` as the Kubernetes-first runtime and deployment repo.

## Repos Inspected

### 1. `AXIOM-Rule-SIEM-engine`

High-signal configs and docs inspected:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/EVENT_SCHEMA.md`
- `docs/COMMAND_SCHEMA.md`
- `deploy/docker-compose.local.yml`
- `deploy/docker-compose.dataflow.yml`

Observed capabilities:

- Multi-ingress SIEM pipeline: AMQP, MQTT, HTTP ingest, Kafka, Flink/stream-processor.
- Defined normalized event schema and command schema.
- Dedicated rule engine with layered evaluation and incident lifecycle.
- Broker-centric command dispatch and event fan-in.
- InfluxDB-driven telemetry storage, rollups, checks, and webhook notifications.
- Optional dataflow split: ingest -> Kafka -> stream processing -> Axiom consumer.
- Supporting services already present in repo structure:
  - `services/axiom`
  - `services/ingest-gateway`
  - `services/ingest-gateway-envoy`
  - `services/ingest-kafka-proxy`
  - `services/lavinmq-kafka-bridge`
  - `services/stream-processor`
  - `services/stream-processor-flink`
  - `services/intel-hub`
  - `services/strategist`
  - `services/aisoar`

### 2. `Cloud_Console_IDS-IPS`

High-signal configs and docs inspected:

- `README.md`
- `docker-compose.local.yml`
- `k8s/kustomization.yaml`
- `docs/AGENT_COMM_ARCHITECTURE.md`
- `docs/EVENT_PIPELINE_INTEGRATION.md`
- `docs/MQTT_TOPIC_CONTRACT.md`
- `internal/playbook/engine.go`
- `internal/playbook/dispatcher.go`

Observed capabilities:

- Console/API and UI separation already modeled.
- Full event -> incident -> playbook -> command pipeline.
- Risk-policy-driven command dispatch with approval/presence hooks.
- Agent communication abstraction with Redis and RabbitMQ backends.
- MQTT topic contract for device commands and update jobs.
- Rich integration surface:
  - Vision One
  - Wazuh
  - AI/RAG
  - audit/logging
  - approvals
  - incidents
  - evidence
  - messaging
- Existing observability and platform manifests for Kubernetes deployment.

### 3. `SOAR_K8S`

High-signal files inspected:

- `readme.md`
- `xdr-soar-infra/README.md`
- `docs/structure.md`
- `xdr-soar-infra/4-data-layer/00-secrets.yaml`
- `xdr-soar-infra/4-data-layer/services.yaml`
- `xdr-soar-infra/5-security-engine/combined-engine.yaml`
- `xdr-soar-infra/5-security-engine/services.yaml`
- `xdr-soar-infra/6-frontend-ui/combined-frontend.yaml`
- `xdr-soar-infra/6-frontend-ui/ingress.yaml`
- `xdr-soar-infra/8-scripts/deploy-all.sh`
- `xdr-soar-infra/apps/detection-engine/main.py`
- `xdr-soar-infra/apps/ml-training/main.py`
- `xdr-soar-infra/apps/yara-scanner/main.py`
- `xdr-soar-infra/apps/firmware-api/main.py`

Observed current state:

- Strong Kubernetes and network-isolation baseline.
- Data layer is present: Kafka, MongoDB, InfluxDB, Redis, MQTT, Supabase.
- Security engine exists mostly as placeholder runtime components.
- Frontends are thin placeholders.
- Firmware download path is implemented.
- Deployment automation and TLS/bootstrap handling are already solid.

## Current Gap Analysis

`SOAR_K8S` currently has infrastructure, but not the full runtime planes found in the other two repos.

Missing or underdeveloped areas:

1. No normalized event-ingest/control plane equivalent to AXIOM's ingest pipeline.
2. No real rule engine comparable to `services/axiom`.
3. No stream normalization or broker-to-bus bridge equivalent to:
   - `lavinmq-kafka-bridge`
   - `stream-processor`
   - `stream-processor-flink`
4. No incident state machine or correlation workflow.
5. No SOAR control plane equivalent to Cloud Console's playbook engine, approval workflow, dispatcher, and audit model.
6. No agent command/result reconciliation model matching AXIOM command schema or Cloud Console dispatcher behavior.
7. No integration plane for external intel and enterprise tools such as Vision One, Wazuh, or threat intel feeds.
8. Current `detection-engine` is a simple HTTP scorer and alert poster, not a SIEM/SOAR orchestration runtime.
9. Current frontend manifests expose UI shells, but not the operational screens needed for incidents, playbooks, approvals, command status, messaging, or integrations.

## Expansion Principles

1. Keep `SOAR_K8S` as the deployment and runtime integration repo.
2. Import or re-implement mature services from the other repos instead of expanding the current placeholder Python apps indefinitely.
3. Standardize on one canonical event schema and one canonical command schema before merging features.
4. Separate data plane, decision plane, and control plane.
5. Preserve the repo's zero-trust and isolated-runtime assumptions.

## Target Runtime Model For `SOAR_K8S`

### Plane 1: Event/Data Plane

- Endpoint/agent telemetry enters through MQTT and/or HTTPS ingest.
- A broker bridge normalizes and forwards events into Kafka.
- A stream processor enriches, deduplicates, validates schema, and emits cleaned topics.
- Cleaned telemetry is stored in InfluxDB and forwarded to the rule/correlation plane.

Primary source repo: `AXIOM-Rule-SIEM-engine`

### Plane 2: Detection/Correlation Plane

- A real rule engine consumes normalized events.
- Layer-1 handles threshold, suppression, allow/deny, and short-window correlation.
- Layer-2 handles sequence/state-machine correlation and external enrichment.
- Incidents become first-class records in Supabase/Postgres.

Primary source repo: `AXIOM-Rule-SIEM-engine`

### Plane 3: SOAR Control Plane

- Incident processing selects playbooks.
- Risk policy determines whether a command is automatic, gated, or approval-required.
- Commands are dispatched through MQTT/AMQP with durable tracking.
- ACK/result/audit trail is persisted.

Primary source repo: `Cloud_Console_IDS-IPS`

### Plane 4: Human and Integration Plane

- Console API exposes incidents, playbooks, approvals, evidence, integrations, and command status.
- Frontends provide dashboard, admin, messaging, and investigation workflows.
- External intel and product integrations enrich detections and support response actions.

Primary source repo: `Cloud_Console_IDS-IPS`

## Planned Workstreams

## Workstream A: Canonical Schemas And Contracts

Adopt AXIOM's event and command contracts as the baseline:

- Event contract from `docs/EVENT_SCHEMA.md`
- Command contract from `docs/COMMAND_SCHEMA.md`

Merge in Cloud Console messaging requirements:

- MQTT topic contract from `docs/MQTT_TOPIC_CONTRACT.md`
- approval/presence semantics from playbook dispatcher

Deliverables:

- `SOAR_K8S/docs/event-schema.md`
- `SOAR_K8S/docs/command-schema.md`
- `SOAR_K8S/docs/messaging-contract.md`
- versioned schema validation in runtime services

## Workstream B: Ingest And Message Transport

Bring in AXIOM's missing transport pieces:

- HTTP ingest gateway
- broker-to-Kafka bridge
- stream processor
- optional Envoy edge tier

Recommended repo additions under `SOAR_K8S/xdr-soar-infra/apps/`:

- `ingest-gateway/`
- `ingest-kafka-proxy/`
- `mq-bridge/`
- `stream-processor/`

Manifest additions under `5-security-engine/` or a new `5-event-plane/`:

- Deployments and Services for each new runtime
- Kafka topics/bootstrap job
- ConfigMaps for routing and schema validation

## Workstream C: Rule Engine Migration

Replace the placeholder `detection-engine` with a real service based on AXIOM's runtime.

Required capability lift:

- consume normalized events from Kafka or broker
- layered rule evaluation
- incident creation
- correlation state
- response command generation
- optional Influx-trigger handling

Recommended change:

- retire current placeholder-only `apps/detection-engine/main.py` role
- replace with either:
  - a port of `services/axiom`, or
  - a new service explicitly derived from it

Persistence targets:

- incident records in Supabase/Postgres
- telemetry metrics in InfluxDB
- correlation cache/state in Redis where low-latency state is needed

## Workstream D: SOAR Playbook And Approval Plane

Adopt Cloud Console's control-plane concepts:

- detector-rule to incident processing
- playbook selection and execution
- risk policy engine
- approval workflow
- command dispatcher
- audit trail

Recommended repo additions:

- `apps/soar-api/`
- `apps/playbook-engine/`

Primary feature set:

- `/api/v1/incidents`
- `/api/v1/playbooks`
- `/api/v1/commands`
- `/api/v1/approvals`
- `/api/v1/audit`
- `/api/v1/agents`
- `/api/v1/integrations`

This is the largest functional gap between `SOAR_K8S` and `Cloud_Console_IDS-IPS`.

## Workstream E: Agent Command And Response Fabric

Unify AXIOM and Cloud command delivery:

- AXIOM contributes command schema and reconciliation model.
- Cloud contributes dispatcher behavior, approval gating, and agent comm abstractions.

Recommended target transport model:

- MQTT for device-facing commands and updater notifications.
- AMQP or Kafka for internal backend workflow events.
- durable queue/topic naming aligned to:
  - `jobs/commands/{device_id}`
  - `jobs/commands/notify/{device_id}`
  - backend command/result topics with correlation IDs

Required records:

- command
- command_delivery
- command_ack
- command_result
- approval_request
- approval_decision

## Workstream F: Integration And Threat Intel Plane

Bring in the mature integration surfaces missing from `SOAR_K8S`:

- threat-intel fetch/enrichment from AXIOM `intel-hub`
- Vision One integration from Cloud Console
- Wazuh integration from Cloud Console
- evidence and investigation data APIs

Recommended repo additions:

- `apps/intel-hub/`
- `apps/integration-worker/`

Data flow:

- external intel enriches incidents and entities
- external response products can receive approved response actions
- investigation UI reads enriched artifacts from Supabase/Postgres and object stores

## Workstream G: Frontend Expansion

Current `admin-frontend` and `soar-dashboard` are only shells. Expand them into operational consoles derived from Cloud Console feature boundaries.

Required UI domains:

- incident list and detail
- alert timeline
- playbook execution status
- approvals queue
- command status and reconciliation
- agent/device inventory
- messaging/transport health
- integration settings
- observability shortcuts

Ingress should no longer route only to firmware and static UIs. Add API routing for the new control plane.

## Workstream H: Data Model And Storage

Use the existing data layer, but assign clearer ownership:

- Supabase/Postgres:
  - incidents
  - detector_rules
  - playbooks
  - playbook_executions
  - commands
  - approvals
  - audit_logs
  - integration_configs
- InfluxDB:
  - high-frequency telemetry
  - rollups
  - anomaly/risk trends
- MongoDB/GridFS:
  - model artifacts
  - firmware artifacts
  - optional evidence blobs
- Redis:
  - correlation cache
  - dedupe windows
  - transient workflow state

## Proposed Repo Changes In `SOAR_K8S`

### New runtime areas

- `xdr-soar-infra/apps/soar-api/`
- `xdr-soar-infra/apps/playbook-engine/`
- `xdr-soar-infra/apps/ingest-gateway/`
- `xdr-soar-infra/apps/mq-bridge/`
- `xdr-soar-infra/apps/stream-processor/`
- `xdr-soar-infra/apps/intel-hub/`
- `xdr-soar-infra/apps/integration-worker/`

### New manifest areas

- `xdr-soar-infra/5-event-plane/`
- `xdr-soar-infra/5-security-engine/` updated to deploy the real rule engine
- `xdr-soar-infra/6-frontend-ui/` updated to route UI and API separately
- `xdr-soar-infra/9-observability/` updated with dashboards/alerts for new services

### New docs

- `docs/event-schema.md`
- `docs/command-schema.md`
- `docs/messaging-contract.md`
- `docs/runtime-topology.md`
- `docs/service-migration-map.md`

## Phase Plan

## Phase 0: Design Freeze And Schema Alignment

Objective:

- choose canonical contracts before moving code

Tasks:

- adopt AXIOM event schema
- adopt AXIOM command schema
- merge Cloud MQTT topic contract
- define service boundaries for event plane, rule plane, and control plane

Exit criteria:

- approved schemas and runtime topology docs committed

## Phase 1: Event Plane Bring-Up

Objective:

- make `SOAR_K8S` capable of real event ingest and normalization

Tasks:

- add ingest gateway
- add broker-to-Kafka bridge
- add stream processor
- define Kafka topics and bootstrap jobs
- emit normalized events into InfluxDB and rule-consumption topics

Exit criteria:

- a test agent event can reach Kafka, be normalized, and appear in downstream storage

## Phase 2: Rule Engine Bring-Up

Objective:

- replace placeholder scoring with real detection and incident creation

Tasks:

- port or derive AXIOM rule engine
- implement incident persistence
- implement layer-1 and initial layer-2 rules
- wire threat intel enrichment hooks

Exit criteria:

- normalized events create incidents with correlation IDs and rule provenance

## Phase 3: SOAR Control Plane Bring-Up

Objective:

- add playbooks, approvals, and command dispatch

Tasks:

- add SOAR API
- add playbook engine
- implement risk policy
- implement approval workflow
- implement command dispatch and reconciliation

Exit criteria:

- incident can trigger a playbook, produce a command, and persist command status transitions

## Phase 4: UI And Integrations

Objective:

- expose the system to operators and external products

Tasks:

- replace placeholder UIs with operational views
- add incident, playbook, approvals, and transport health pages
- integrate Vision One, Wazuh, and intel sources
- extend observability dashboards and alerts

Exit criteria:

- operators can investigate, approve, dispatch, and audit from the UI

## Service Migration Map

### Migrate from `AXIOM-Rule-SIEM-engine`

Priority imports:

- `services/axiom`
- `services/ingest-gateway`
- `services/ingest-gateway-envoy`
- `services/ingest-kafka-proxy`
- `services/lavinmq-kafka-bridge`
- `services/stream-processor`
- `services/stream-processor-flink`
- `services/intel-hub`
- `services/strategist`
- schema/docs associated with events and commands

### Migrate from `Cloud_Console_IDS-IPS`

Priority imports:

- playbook engine concepts and persistence model
- approval workflow
- command dispatcher
- agent communication abstraction
- MQTT topic contract
- incident/command/audit API boundaries
- Vision One and Wazuh integration modules
- frontend feature boundaries for ops console

## Recommended Implementation Order

1. Contracts first.
2. Event transport second.
3. Rule engine third.
4. SOAR control plane fourth.
5. UI and external integrations last.

This order keeps `SOAR_K8S` deployable at every stage and avoids building UI around unstable backend contracts.

## Immediate Next Actions

1. Create canonical schema docs in `SOAR_K8S/docs` derived from AXIOM and Cloud contracts.
2. Decide whether the real rule/control-plane services will be vendored into this repo or rebuilt as new services using the source repos as references.
3. Add a new manifest group for the event plane instead of overloading `combined-engine.yaml`.
4. Replace the current placeholder `detection-engine` expansion path with a real AXIOM-derived runtime.
5. Plan the first database migration set for incidents, playbooks, commands, approvals, and audit logs.

## Progress Update

As of 2026-03-30, the following Phase 0 and early Phase 1 items now exist in `SOAR_K8S`:

- canonical docs:
  - `docs/event-schema.md`
  - `docs/command-schema.md`
  - `docs/messaging-contract.md`
- event-plane scaffold:
  - `xdr-soar-infra/5-event-plane/`
  - `apps/ingest-gateway/`
  - `apps/mq-bridge/`
  - `apps/stream-processor/`
- deployment and workflow wiring:
  - `8-scripts/deploy-all.sh`
  - `8-scripts/build-images.sh`
  - `8-scripts/validate-config.sh`

Current maturity:

- repo structure: in place
- contracts: in place
- event-plane runtime: partially implemented
- ingest-gateway Kafka publish path: implemented
- mq-bridge HTTP-to-Kafka bridge path: implemented
- stream-processor Kafka consume/publish path: implemented
- real message-bus integration: not yet implemented
- AXIOM rule engine migration: not yet implemented
- Cloud Console SOAR control plane migration: not yet implemented

## Bottom Line

`SOAR_K8S` already has the cluster, security boundaries, data services, deployment automation, and firmware path. What it lacks is the mature runtime software. The cleanest expansion path is:

- take SIEM/event-processing architecture from `AXIOM-Rule-SIEM-engine`
- take SOAR/control-plane architecture from `Cloud_Console_IDS-IPS`
- keep `SOAR_K8S` as the Kubernetes-native integration and operations repo

That produces a clearer end state than extending the current placeholder services one by one.
