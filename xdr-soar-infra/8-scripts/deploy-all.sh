#!/bin/bash
# XDR/SOAR Infrastructure: Deployment Script (Idempotent)
# 
# This script deploys the entire stack in the correct dependency order.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
RENDER_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$RENDER_DIR"
}

trap cleanup EXIT

if ! command -v envsubst >/dev/null 2>&1; then
  echo "envsubst is required to render deployment templates." >&2
  exit 1
fi

export XDR_SOAR_REQUIRE_PLATFORM_ENV=1
# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-platform-env.sh"

render_template() {
  local source_file="$1"
  local rendered_file="$RENDER_DIR/${source_file#"$ROOT_DIR/"}"

  mkdir -p "$(dirname "$rendered_file")"
  envsubst < "$source_file" > "$rendered_file"
  printf '%s\n' "$rendered_file"
}

apply_rendered_dir() {
  local source_dir="$1"

  while IFS= read -r manifest; do
    kubectl apply -f "$(render_template "$manifest")"
  done < <(find "$source_dir" -maxdepth 1 -type f \( -name '*.yaml' -o -name '*.yml' \) | sort)
}

echo "[$(date)] Starting XDR/SOAR Infrastructure deployment..."

# 1. Create Namespace (Idempotent)
echo "[$(date)] Applying Namespace..."
kubectl apply -f "$SCRIPT_DIR/../2-kubernetes-cluster/00-namespace.yaml"

# 1.5 Platform TLS issuer when cert-manager CRDs are present.
if kubectl api-resources --api-group=cert-manager.io 2>/dev/null | grep -q '^clusterissuers'; then
  echo "[$(date)] Applying ClusterIssuer..."
  kubectl apply -f "$(render_template "$ROOT_DIR/2-kubernetes-cluster/01-clusterissuer.yaml")"
else
  echo "[$(date)] Skipping ClusterIssuer because cert-manager CRDs are not present in the target cluster."
fi

# 2. Network Policies
echo "[$(date)] Applying Network Policies..."
kubectl apply -f "$SCRIPT_DIR/../3-k8s-network-policies/"

# 3. Data Layer (Secrets, Services, StatefulSets, then stateless dependencies)
echo "[$(date)] Applying Data Layer (Kafka, MongoDB, InfluxDB, etc.)..."
kubectl apply -f "$(render_template "$ROOT_DIR/4-data-layer/00-secrets.yaml")"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/services.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/mongodb/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/influxdb/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/kafka/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/mqtt/deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/redis/deployment.yaml"
apply_rendered_dir "$ROOT_DIR/4-data-layer/supabase"

# 4. Security Engine (Inference servers, Rules, Scanners)
echo "[$(date)] Applying Security Engine..."
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/services.yaml"
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/model-repository-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/combined-engine.yaml"
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/firmware-api.yaml"

# 5. Frontend UI
echo "[$(date)] Applying Frontend UI..."
kubectl apply -f "$SCRIPT_DIR/../6-frontend-ui/combined-frontend.yaml"
kubectl apply -f "$(render_template "$ROOT_DIR/6-frontend-ui/ingress.yaml")"

# 6. Observability
echo "[$(date)] Applying Observability Stack..."
kubectl apply -f "$SCRIPT_DIR/../9-observability/"

echo "[$(date)] Deployment finished. Run 'kubectl get pods -n xdr-soar' to monitor status."
