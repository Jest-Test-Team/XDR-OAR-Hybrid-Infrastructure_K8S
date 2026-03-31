# Repo Status Report

Date: 2026-03-27
Scope: `note.txt`, `xdr-soar-infra/`, `readme.md`, and deployment/validation assets

## Current State

- `note.txt` is empty, so it does not add extra requirements.
- `xdr-soar-infra/1-vmware-esxi/` is now one coherent Terraform root with versions, providers, variables, outputs, example tfvars, and automated validation coverage.
- Kubernetes deployment remains YAML-first, but the repo now bootstraps platform config, auto-selects TLS mode, renders environment-specific Secrets, Supabase URLs, Ingress hosts, MQTT exposure, and TLS settings at deploy time.
- Every third-party image referenced by tracked Kubernetes manifests is now pinned to an immutable digest.
- The Windows updater is no longer tied to embedded `.local` endpoints or blank MQTT credentials; it requires external runtime config.

## Implemented From The Original Gap List

- generated bootstrap secrets via `xdr-soar-infra/8-scripts/generate-platform-secrets.sh`
- added `xdr-soar-infra/8-scripts/bootstrap-platform-config.sh`, `xdr-soar-infra/8-scripts/load-platform-env.sh`, and `xdr-soar-infra/config/platform.env.example` so active manifests stop carrying fake operational values and can still deploy without manual pre-seeding
- moved Supabase auth and REST to secret-backed DB URLs instead of inline `change-me` DSNs
- added TLS blocks and cert-manager ClusterIssuer wiring for the frontend ingress
- removed `.local` host assumptions from active manifests and runtime automation
- updated the Windows updater to load broker credentials, broker certificate thumbprint, and firmware API URL from JSON config or environment variables
- added generated TLS assets, MQTT broker auth bootstrap, an external MQTT service, automatic TLS-mode selection, and a packaged Windows updater bundle so the updater path is deployable end to end from repo automation
- made `install-cilium.sh` auto-detect the Kubernetes API server endpoint when explicit values are not supplied
- pinned the remaining vendor images to digests, including Redis, MongoDB, InfluxDB, Kafka, EMQX, Kong, PostgREST, Prometheus, Grafana, Loki, Promtail, Supabase Postgres, and Triton
- extended validation so it rejects stale placeholders, `:latest`, and tag-only third-party images
- added a dedicated GitLab Terraform validation job and Dockerized Terraform fallback for local validation

## What Is Still Left

There are no remaining repo-level feature TODOs from the inspected list.

The remaining decisions are optional production hardening only:

- rotate or externalize the generated bootstrap secrets before production rollout
- switch the default bootstrap TLS flow to organization-managed PKI if required by the target environment

## Verification Notes

- `validate-config.sh` is now designed to validate Terraform with either local Terraform or a Dockerized fallback, plus YAML, Python, placeholder, and digest checks
- the image digests were verified against primary registry metadata sources documented in `xdr-soar-infra/IMAGE-PINNING.md`
