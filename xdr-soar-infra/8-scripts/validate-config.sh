#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$ROOT_DIR/1-vmware-esxi"

echo "[$(date)] Validating Terraform formatting..."
if command -v terraform >/dev/null 2>&1; then
  terraform -chdir="$TERRAFORM_DIR" fmt -check
  if [ -d "$TERRAFORM_DIR/.terraform" ]; then
    terraform -chdir="$TERRAFORM_DIR" validate
  else
    echo "[$(date)] Skipping terraform validate because $TERRAFORM_DIR/.terraform is missing."
  fi
else
  echo "[$(date)] Skipping Terraform checks because terraform is not installed."
fi

echo "[$(date)] Validating Kubernetes manifest YAML syntax..."
if command -v ruby >/dev/null 2>&1; then
  while IFS= read -r manifest; do
    ruby -e 'require "yaml"; YAML.load_stream(File.read(ARGV[0]))' "$manifest" >/dev/null
  done < <(
    find \
      "$ROOT_DIR/2-kubernetes-cluster" \
      "$ROOT_DIR/3-k8s-network-policies" \
      "$ROOT_DIR/4-data-layer" \
      "$ROOT_DIR/5-security-engine" \
      "$ROOT_DIR/6-frontend-ui" \
      -type f \( -name '*.yaml' -o -name '*.yml' \) ! -name 'cilium-values.yaml' | sort
  )
else
  echo "[$(date)] Skipping manifest syntax checks because ruby is not installed."
fi

echo "[$(date)] Validation completed."
