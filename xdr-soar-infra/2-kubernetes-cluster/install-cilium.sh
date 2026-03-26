#!/bin/bash

set -euo pipefail

: "${K8S_API_SERVER_HOST:?Set K8S_API_SERVER_HOST before running this script.}"
: "${K8S_API_SERVER_PORT:=6443}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VALUES_FILE="$SCRIPT_DIR/cilium-values.yaml"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required to install Cilium." >&2
  exit 1
fi

if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst is required to render cilium-values.yaml." >&2
  exit 1
fi

helm repo add cilium https://helm.cilium.io >/dev/null
helm repo update >/dev/null

envsubst < "$VALUES_FILE" | helm upgrade --install cilium cilium/cilium \
  --namespace kube-system \
  --create-namespace \
  -f -
