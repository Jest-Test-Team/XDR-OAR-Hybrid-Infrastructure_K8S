# Repo Inspection Report

Date: 2026-03-26
Scope: repository structure, docs, Terraform, Kubernetes manifests, deployment script, and Windows updater stub.

## Overall Assessment

This repo is currently closer to an architecture scaffold than a deployable infrastructure package.

The strongest parts are the high-level intent and system decomposition in `readme.md` and `structure.md`.
The main gaps are:

- the Kubernetes package is incomplete for a real cluster rollout
- the network policy set blocks most inter-service traffic
- several manifests are placeholders rather than runnable workloads
- the docs describe more than the repo actually deploys

## Critical Findings

### 1. Namespace-wide default deny breaks the current app topology

`xdr-soar-infra/3-k8s-network-policies/00-default-deny-all.yaml` denies both ingress and egress for all pods, but the repo only adds:

- one MQTT ingress exception in `xdr-soar-infra/3-k8s-network-policies/01-allow-mqtt-ingress.yaml`
- one YARA egress exception in `xdr-soar-infra/3-k8s-network-policies/02-isolate-yara.yaml`

That means the following documented flows are blocked by default:

- detection engine -> InfluxDB (`xdr-soar-infra/5-security-engine/1-detection-engine.yaml:19-21`)
- Triton -> model repository storage (`xdr-soar-infra/5-security-engine/2-ml-models-triton.yaml:17-19`)
- ML retraining job -> any external/internal dependency (`xdr-soar-infra/5-security-engine/3-ml-training-cronjob.yaml:7-15`)
- most pods -> DNS, unless explicitly allowed

Suggestion:

- add a baseline DNS egress policy
- define explicit service-to-service allow rules from the real data flow diagram
- validate the final matrix against the Mermaid diagram in `structure.md`

### 2. No Kubernetes Services exist for workloads that are referenced by DNS name

There are no `Service` manifests in the repo, while workloads assume stable service discovery:

- `serviceName: "kafka"` in `xdr-soar-infra/4-data-layer/kafka/statefulset.yaml:7`
- `serviceName: "mongodb"` in `xdr-soar-infra/4-data-layer/mongodb/statefulset.yaml:8`
- `serviceName: "influxdb"` in `xdr-soar-infra/4-data-layer/influxdb/statefulset.yaml:7`
- `INFLUXDB_URL=http://influxdb:8086` in `xdr-soar-infra/5-security-engine/1-detection-engine.yaml:19-21`

Suggestion:

- create headless Services for StatefulSets
- create ClusterIP Services for app-to-app access
- add an ingress strategy for UI/API exposure instead of relying on pod IPs

### 3. Deployment script is incomplete and not idempotent

`xdr-soar-infra/8-scripts/deploy-all.sh`:

- uses `kubectl create namespace xdr-soar` and will fail on rerun (`line 3`)
- applies only network policies, MQTT, MongoDB, and the security engine (`lines 4-7`)
- does not deploy Kafka, InfluxDB, Redis, Supabase, UI, or Cilium values

Suggestion:

- make the namespace creation idempotent
- define deployment order by dependency
- switch to `kustomize` or Helm so one command deploys a consistent stack

### 4. Several images are placeholders and cannot be reproduced from this repo

These images are referenced but there is no source or Docker build path for them here:

- `custom-engine:latest`
- `custom-yara:latest`
- `ml-training:latest`
- `soar-frontend:latest`
- `admin-frontend:latest`

Also `supabase/postgres:latest` is not a full Supabase deployment; it is only a Postgres image placeholder in `xdr-soar-infra/4-data-layer/supabase/deployment.yaml:1-19`.

Suggestion:

- define which images are external dependencies vs. built from this repo
- add Dockerfiles and CI build steps for internal images
- pin every image to immutable tags or digests

### 5. Stateful/data workloads have no persistence or operating configuration

MongoDB, Kafka, and InfluxDB are missing the minimum setup needed for real use:

- no `volumeClaimTemplates`
- no `volumes` / `volumeMounts`
- no ports
- no env/config for clustering or auth
- no probes
- no resource requests/limits

References:

- `xdr-soar-infra/4-data-layer/kafka/statefulset.yaml:1-19`
- `xdr-soar-infra/4-data-layer/mongodb/statefulset.yaml:1-20`
- `xdr-soar-infra/4-data-layer/influxdb/statefulset.yaml:1-19`

Suggestion:

- start with single-node, persistent, authenticated versions of each dependency
- only then add HA/replica behavior

## Security and Reliability Gaps

### 6. `latest` tags are used across the stack

Examples:

- `confluentinc/cp-kafka:latest`
- `nvcr.io/nvidia/tritonserver:latest`
- `supabase/postgres:latest`
- all custom app images use `:latest`

Suggestion:

- replace all `latest` tags with pinned versions or digests

### 7. Terraform vSphere config disables TLS verification

`xdr-soar-infra/1-vmware-esxi/01-network-segmentation.tf:1-15` sets `allow_unverified_ssl = true`.

Suggestion:

- use valid vSphere certificates
- add provider version pinning and variable definitions
- add the missing infrastructure references needed for a real port-group apply

### 8. YARA pod hardening is incomplete and one field is in the wrong place

In `xdr-soar-infra/5-security-engine/4-yara-scanner.yaml:15-21`, `readOnlyRootFilesystem` is under pod `securityContext`, but that field belongs on the container security context.

Other missing hardening:

- `allowPrivilegeEscalation: false`
- `seccompProfile`
- capability drop list
- writable scratch volume if the container needs temp files

### 9. Windows updater is only a stub and does not verify an expected digest

`xdr-soar-infra/7-windows-agents/mqtt-pull-updater.ps1:1-18`:

- hardcodes `mqtt.local` and `api.local`
- computes a SHA-256 hash but does not compare it to a trusted expected value
- has no certificate pinning, signature verification, rollback, or MQTT auth/TLS flow

Suggestion:

- define the update contract first: topic schema, auth, expected digest/signature source, retry/rollback behavior

## Documentation and Repo Hygiene

### 10. Docs overstate what the repo actually ships

The top-level docs describe:

- Grafana / Loki / Prometheus
- full data hub coverage
- production-like SOAR/XDR automation

But the repo does not include those manifests, services, secrets, or app code. The deploy script also skips major components.

Suggestion:

- split docs into `current state` vs `target architecture`
- mark placeholder manifests clearly

### 11. `init.py` looks like a repo generator, not runtime code

`init.py` contains embedded file templates for the same repo structure. That is useful for scaffolding, but it should be identified explicitly so it is not mistaken for application code.

Suggestion:

- move it to `tools/` or `scripts/`
- rename it to something like `scaffold_repo.py`
- document when it should be used

## Recommended TODO Order

- [ ] Add a `Namespace` manifest and make deployment idempotent.
- [ ] Add all missing `Service` manifests, especially headless Services for StatefulSets.
- [ ] Replace the current network policies with a tested allow matrix that includes DNS.
- [ ] Add persistent storage, probes, ports, and resource requests/limits for MongoDB, Kafka, and InfluxDB.
- [ ] Decide whether Supabase is truly needed; if yes, model it properly, not as a single Postgres placeholder.
- [ ] Replace all `:latest` tags with pinned versions or digests.
- [ ] Add Secrets and ConfigMaps for credentials, TLS material, cluster config, and app settings.
- [ ] Define how internal images are built and published, then add Dockerfiles and CI steps.
- [ ] Fix container hardening, starting with the YARA manifest.
- [ ] Rewrite `deploy-all.sh` into a reproducible deployment entrypoint using `kustomize` or Helm.
- [ ] Align `readme.md` and `structure.md` with what is implemented today.
- [ ] Define a minimal validation workflow: YAML linting, Kubernetes schema validation, and Terraform formatting/validation.

## Short Conclusion

If the goal is to make this repo operational quickly, the first milestone should be:

1. a single-node but real Kubernetes deployment
2. working service discovery
3. explicit network policy exceptions
4. persistent/authenticated data services
5. pinned, reproducible images

Until those are in place, the repo is best treated as a design baseline rather than a production-ready infrastructure repository.
