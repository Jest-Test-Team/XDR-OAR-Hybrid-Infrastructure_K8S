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
"$SCRIPT_DIR/generate-tls-assets.sh" >/dev/null
"$SCRIPT_DIR/package-windows-updater-bundle.sh" "$ROOT_DIR/.generated/windows-updater-bundle" "$ROOT_DIR/.generated/windows-updater-bundle.zip" >/dev/null

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

echo "[$(date)] Using platform domain $XDR_SOAR_BASE_DOMAIN and MQTT endpoint ${MQTT_BROKER_HOST}:${MQTT_BROKER_PORT}"

# 1. Create Namespace (Idempotent)
echo "[$(date)] Applying Namespace..."
kubectl apply -f "$SCRIPT_DIR/../2-kubernetes-cluster/00-namespace.yaml"

CERT_MANAGER_AVAILABLE=0
if kubectl api-resources --api-group=cert-manager.io 2>/dev/null | grep -q '^clusterissuers'; then
  CERT_MANAGER_AVAILABLE=1
fi

EFFECTIVE_TLS_MODE="$XDR_SOAR_TLS_MODE"
if [ "$EFFECTIVE_TLS_MODE" = "auto" ]; then
  if [ "$CERT_MANAGER_AVAILABLE" = "1" ]; then
    EFFECTIVE_TLS_MODE="cert-manager"
  else
    EFFECTIVE_TLS_MODE="selfsigned"
  fi
fi

# 1.5 TLS assets for ingress and MQTT.
if [ "$EFFECTIVE_TLS_MODE" = "cert-manager" ] && [ "$CERT_MANAGER_AVAILABLE" = "1" ]; then
  echo "[$(date)] Applying ClusterIssuer..."
  kubectl apply -f "$(render_template "$ROOT_DIR/2-kubernetes-cluster/01-clusterissuer.yaml")"
else
  echo "[$(date)] Applying locally generated ingress TLS secret..."
  kubectl create secret tls "$XDR_SOAR_TLS_SECRET_NAME" \
    --namespace xdr-soar \
    --cert "$ROOT_DIR/.generated/tls/platform.crt" \
    --key "$ROOT_DIR/.generated/tls/platform.key" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

echo "[$(date)] Applying MQTT TLS secret..."
kubectl create secret generic "$XDR_SOAR_MQTT_TLS_SECRET_NAME" \
  --namespace xdr-soar \
  --from-file=tls.crt="$ROOT_DIR/.generated/tls/mqtt.crt" \
  --from-file=tls.key="$ROOT_DIR/.generated/tls/mqtt.key" \
  --from-file=ca.crt="$ROOT_DIR/.generated/tls/ca.crt" \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. Network Policies
echo "[$(date)] Applying Network Policies..."
kubectl apply -f "$SCRIPT_DIR/../3-k8s-network-policies/"

# 3. Data Layer (Secrets, Services, StatefulSets, then stateless dependencies)
echo "[$(date)] Applying Data Layer (Kafka, MongoDB, InfluxDB, etc.)..."
kubectl apply -f "$(render_template "$ROOT_DIR/4-data-layer/00-secrets.yaml")"
kubectl apply -f "$(render_template "$ROOT_DIR/4-data-layer/services.yaml")"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/mongodb/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/influxdb/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/kafka/statefulset.yaml"
kubectl apply -f "$(render_template "$ROOT_DIR/4-data-layer/mqtt/00-configmap.yaml")"
kubectl apply -f "$(render_template "$ROOT_DIR/4-data-layer/mqtt/deployment.yaml")"
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

echo "[$(date)] Deployment finished. Generated Windows updater config: $ROOT_DIR/.generated/updater-config.json"
echo "[$(date)] Generated Windows updater bundle: $ROOT_DIR/.generated/windows-updater-bundle.zip"
