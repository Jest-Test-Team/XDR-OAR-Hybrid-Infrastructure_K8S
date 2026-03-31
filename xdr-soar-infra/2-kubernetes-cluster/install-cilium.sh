#!/bin/bash

set -euo pipefail

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

if [ -z "${K8S_API_SERVER_HOST:-}" ] || [ -z "${K8S_API_SERVER_PORT:-}" ]; then
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required to auto-detect the Kubernetes API server endpoint." >&2
    exit 1
  fi

  KUBE_API_SERVER="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
  KUBE_API_SERVER="${KUBE_API_SERVER#https://}"
  K8S_API_SERVER_HOST="${KUBE_API_SERVER%%:*}"
  if [ "$K8S_API_SERVER_HOST" = "$KUBE_API_SERVER" ]; then
    K8S_API_SERVER_PORT=443
  else
    K8S_API_SERVER_PORT="${KUBE_API_SERVER##*:}"
  fi
fi

export K8S_API_SERVER_HOST
export K8S_API_SERVER_PORT

echo "[$(date)] Rendering Cilium values for API server $K8S_API_SERVER_HOST:$K8S_API_SERVER_PORT"

helm repo add cilium https://helm.cilium.io >/dev/null
helm repo update >/dev/null

envsubst < "$VALUES_FILE" | helm upgrade --install cilium cilium/cilium \
  --namespace kube-system \
  --create-namespace \
  -f -
