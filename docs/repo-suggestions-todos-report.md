# Repo Inspection Report

Date: 2026-03-26
Scope: `note.txt`, `xdr-soar-infra/`, `readme.md`, and `docs/structure.md`

## Quick Snapshot

- `note.txt` is empty (`0` bytes), so it did not provide extra requirements or TODO context.
- `xdr-soar-infra/` currently contains only two Terraform files:
  - `xdr-soar-infra/1-vmware-esxi/01-network-segmentation.tf`
  - `xdr-soar-infra/1-vmware-esxi/1-vmware-esxi/main.tf`
- The Kubernetes side is broader than before: namespace, Cilium values, five network policies, data-layer manifests, engine manifests, frontend manifests, a deployment script, and a Windows updater stub all exist.
- The previous version of this report had become stale; it no longer matched the current file tree.

## Overall Assessment

The repo is now a more complete scaffold than the earlier report described, but the Terraform layer is still very thin and fragmented.

Your concern about "missing tons of Terraform" is directionally correct:

- there is no coherent Terraform root for the hybrid stack
- there are no supporting Terraform files for variables, versions, outputs, or backend config
- most of the actual infrastructure is still managed only as raw YAML plus a shell script

In other words, this repo now has "more Kubernetes manifests than before", but it still does not have a Terraform story that matches the architecture described in `readme.md` and `docs/structure.md`.

## Critical Findings

### 1. The Terraform layer is fragmented into two unrelated roots and is missing the usual supporting files

Only two `.tf` files exist in the entire repo:

- `xdr-soar-infra/1-vmware-esxi/01-network-segmentation.tf`
- `xdr-soar-infra/1-vmware-esxi/1-vmware-esxi/main.tf`

Problems:

- `xdr-soar-infra/1-vmware-esxi/01-network-segmentation.tf:1-15` is one standalone root.
- `xdr-soar-infra/1-vmware-esxi/1-vmware-esxi/main.tf:1-18` is a second, nested root.
- Running Terraform in `xdr-soar-infra/1-vmware-esxi/` will not automatically include the nested `1-vmware-esxi/main.tf`.
- There is no `terraform {}` block anywhere in the repo.
- There are no provider version constraints.
- There is no `variables.tf`.
- There is no `outputs.tf`.
- There is no example `.tfvars` file.
- There is no backend configuration.

Suggestion:

- decide whether `xdr-soar-infra/1-vmware-esxi/` is one Terraform root or a modules folder
- flatten the accidental nested root
- add at minimum: `versions.tf`, `providers.tf`, `variables.tf`, `outputs.tf`, and `terraform.tfvars.example`

### 2. The current Terraform content is not self-contained

`xdr-soar-infra/1-vmware-esxi/01-network-segmentation.tf:2-4` references:

- `var.vsphere_user`
- `var.vsphere_password`
- `var.vsphere_server`

But there are no matching `variable` declarations anywhere in the repo.

That means the vSphere Terraform cannot be understood or reused from this repository alone.

Suggestion:

- declare the missing input variables
- document required credentials and expected object names
- add outputs for created network objects so later layers can consume them cleanly

### 3. The Terraform scope does not match the architecture the docs describe

The architecture docs describe a hybrid stack spanning:

- VMware network segmentation
- a Kubernetes cluster
- Cilium networking
- data services
- detection services
- frontend services

But the actual Terraform only covers:

- one vSphere provider block and one distributed port group in `xdr-soar-infra/1-vmware-esxi/01-network-segmentation.tf:1-15`
- one Helm release for MongoDB in `xdr-soar-infra/1-vmware-esxi/1-vmware-esxi/main.tf:1-18`

What is missing from Terraform, if the repo is meant to be Terraform-driven:

- VMware app-network resources for the VLAN 20 side described in `docs/structure.md:10-14`
- any VM provisioning for the Kubernetes node(s) or Windows test node shown in `docs/structure.md:16-47`
- any Terraform-managed firewall or NSX-style network segmentation implied by `docs/structure.md:51-54`
- any Terraform-managed namespace, Cilium install, network policies, data services, security engine, or frontend rollout

Suggestion:

- either move decisively to Terraform/Helm ownership for the stack
- or explicitly document that Terraform only handles a small VMware subset and everything else is YAML-driven

### 4. The README deployment instructions do not match the current repo layout

`readme.md:73-77` tells the user to run:

```bash
cd 1-vmware-esxi/
terraform init && terraform apply
```

But the real path is `xdr-soar-infra/1-vmware-esxi/`.

Also:

- `readme.md:81-85` says `kubectl apply -f 2-kubernetes-cluster/cilium-values.yaml`
- `xdr-soar-infra/2-kubernetes-cluster/cilium-values.yaml:1-8` is a Helm values file, not a Kubernetes manifest
- `xdr-soar-infra/2-kubernetes-cluster/cilium-values.yaml:3` still contains the placeholder `API_SERVER_IP`

Suggestion:

- fix all documented paths to include `xdr-soar-infra/`
- document Cilium installation as a Helm values input, not a `kubectl apply`
- replace placeholders like `API_SERVER_IP` with actual parameterization

### 5. The current network policies do not fully implement the stated zero-trust design

The repo now has more network-policy coverage than the old report claimed, but there are still design mismatches.

Most important issue:

- `xdr-soar-infra/3-k8s-network-policies/02-isolate-yara.yaml:6-17` says YARA should only egress to MongoDB
- `xdr-soar-infra/3-k8s-network-policies/04-internal-allow-rules.yaml:40-77` grants egress from `podSelector: {}` to Kafka, MongoDB, InfluxDB, Supabase, and Triton
- because `podSelector: {}` matches all pods, YARA is no longer isolated in practice

Other mismatches:

- `docs/structure.md:61-64` shows admin-triggered update flow through MQTT, but there is no rule allowing the UI workloads to talk to `mqtt-broker`
- `docs/structure.md:68-78` shows a richer service matrix than the policies currently spell out explicitly
- the current policy shape is still broad: `internal-allow-rules` grants common egress from every pod rather than from named producers only

Suggestion:

- keep DNS as a baseline rule
- replace `podSelector: {}` egress with workload-specific rules
- decide whether YARA is truly MongoDB-only, or whether Kafka writeback is part of the real design

### 6. Stateful services are improved, but they are still not modeled as fully operational data services

The old report was wrong to say MongoDB, Kafka, and InfluxDB had no PVCs or probes. They do now:

- Kafka: `xdr-soar-infra/4-data-layer/kafka/statefulset.yaml:1-66`
- MongoDB: `xdr-soar-infra/4-data-layer/mongodb/statefulset.yaml:1-55`
- InfluxDB: `xdr-soar-infra/4-data-layer/influxdb/statefulset.yaml:1-51`

The remaining gaps are different:

- the Services in `xdr-soar-infra/4-data-layer/services.yaml:1-75` are normal Services, not headless Services, even though the StatefulSets use `serviceName`
- `xdr-soar-infra/8-scripts/deploy-all.sh:22-25` applies StatefulSets before applying their Services
- MongoDB has no auth configuration
- InfluxDB has persistence but no bootstrap config for org, bucket, admin token, or onboarding
- Supabase is still represented as one Postgres container in `xdr-soar-infra/4-data-layer/combined-deployments.yaml:75-112`, not a real Supabase stack
- `POSTGRES_PASSWORD` is hardcoded inline in `xdr-soar-infra/4-data-layer/combined-deployments.yaml:102-104`

Suggestion:

- create headless Services where StatefulSet DNS identity matters
- apply Services before StatefulSets
- move credentials into Secrets
- define minimum bootstrap/config for each stateful dependency

### 7. Several components are still placeholders with no source or build path in this repo

These images are referenced in manifests but have no corresponding build context or source code here:

- `custom-engine:v1.0.0` in `xdr-soar-infra/5-security-engine/combined-engine.yaml:17-18`
- `ml-training:v1.0.0` in `xdr-soar-infra/5-security-engine/combined-engine.yaml:86-88`
- `custom-yara:v1.0.0` in `xdr-soar-infra/5-security-engine/combined-engine.yaml:117-118`
- `admin-frontend:v1.0.0` in `xdr-soar-infra/6-frontend-ui/combined-frontend.yaml:17-18`
- `soar-frontend:v1.0.0` in `xdr-soar-infra/6-frontend-ui/combined-frontend.yaml:63-64`

Related gaps:

- there are no Dockerfiles for these images
- there is no CI build pipeline for them
- the frontends only have internal Services in `xdr-soar-infra/6-frontend-ui/combined-frontend.yaml:35-45` and `xdr-soar-infra/6-frontend-ui/combined-frontend.yaml:81-91`
- there is no Ingress, Gateway, or LoadBalancer strategy for actually reaching the UIs

Suggestion:

- separate "external dependency images" from "images built by this repo"
- add Dockerfiles and CI for internal images
- define how the dashboard and admin panel are exposed

### 8. The GitLab pipeline and Windows updater are still partial and internally inconsistent

`xdr-soar-infra/.gitlab-ci.yml:6-23` references files that do not exist in this repo:

- `agent_main.py`
- `scripts/upload_to_gridfs.py`

It also publishes to `mqtt.local`, while the PowerShell updater expects `mqtt.xdr-soar.local` in `xdr-soar-infra/7-windows-agents/mqtt-pull-updater.ps1:6-9`.

The updater itself is improved compared with the old report because it now checks the expected SHA-256, but it is still not runnable as a real agent listener:

- `xdr-soar-infra/7-windows-agents/mqtt-pull-updater.ps1:64` logs `$Topic`, which is undefined
- `xdr-soar-infra/7-windows-agents/mqtt-pull-updater.ps1:65-66` explicitly says the real MQTT client implementation is still missing
- the binary replacement step is still commented out in `xdr-soar-infra/7-windows-agents/mqtt-pull-updater.ps1:51-52`

Suggestion:

- align hostnames between CI, services, and the Windows agent
- add the missing build/upload code or remove the broken pipeline references
- finish the actual MQTT subscription and update-apply flow

## Repo Hygiene Notes

### 9. Some directory names imply per-component manifests that do not actually exist

These directories are present but empty:

- `xdr-soar-infra/4-data-layer/mqtt/`
- `xdr-soar-infra/4-data-layer/redis/`
- `xdr-soar-infra/4-data-layer/supabase/`

At the same time, the actual manifests live in:

- `xdr-soar-infra/4-data-layer/combined-deployments.yaml`
- `xdr-soar-infra/4-data-layer/services.yaml`

This is not a runtime bug, but it makes the repo look more complete and more componentized than it really is.

Suggestion:

- either move each component into its own directory with its own manifests
- or remove the empty folders and document that the data layer is intentionally combined

### 10. The docs still overstate completion

`readme.md:97-114` says the repo already completed the improvements from this report.

Some of those claims are now true, but not all of them:

- idempotent namespace apply: true
- Services now exist: true
- PVCs and probes for core stateful services: true
- Terraform completeness: still false
- deploy docs correctness: still false
- Cilium install instructions: still false
- fully aligned network policy matrix: still false
- real Supabase implementation: still false
- image build ownership: still false

The docs also still advertise observability components in `readme.md:52` that do not exist under `xdr-soar-infra/`.

Suggestion:

- split docs into `implemented today` and `target architecture`
- stop marking unfinished items as already completed

## Recommended TODO Order

- [ ] Decide the ownership model: Terraform-first, YAML-first, or mixed with clear boundaries.
- [ ] Consolidate the Terraform layout into one real root or one root plus explicit modules.
- [ ] Add missing Terraform support files: `versions.tf`, `providers.tf`, `variables.tf`, `outputs.tf`, and `terraform.tfvars.example`.
- [ ] Declare the missing `vsphere_*` variables and add outputs for created VMware resources.
- [ ] Move or remove the nested `xdr-soar-infra/1-vmware-esxi/1-vmware-esxi/` Terraform root.
- [ ] Fix `readme.md` deployment paths and replace the incorrect `kubectl apply` guidance for `cilium-values.yaml`.
- [ ] Replace placeholder values such as `API_SERVER_IP` with real inputs.
- [ ] Rework network policies so YARA isolation and the documented service flows are not contradictory.
- [ ] Apply Services before StatefulSets and decide where headless Services are required.
- [ ] Move inline passwords and future tokens into Kubernetes Secrets.
- [ ] Decide whether "Supabase" is truly required; if yes, model it explicitly instead of as a single Postgres container.
- [ ] Add source/build ownership for `custom-engine`, `ml-training`, `custom-yara`, `admin-frontend`, and `soar-frontend`.
- [ ] Fix the broken GitLab CI references and complete the Windows updater’s MQTT implementation.
- [ ] Align the docs with the actual implemented state, especially the Terraform and observability claims.
- [ ] Add validation gates: `terraform fmt`, `terraform validate`, YAML linting, and Kubernetes schema validation.

## Short Conclusion

The repo is no longer just a blank scaffold, but the Terraform concern is real.

Today, `xdr-soar-infra/` has a partially improved Kubernetes YAML layer and a still-underbuilt Terraform layer. The biggest structural gap is not one missing line inside one `.tf` file; it is that the repo has not yet chosen and implemented a coherent Terraform structure for the hybrid VMware + Kubernetes stack it documents.
