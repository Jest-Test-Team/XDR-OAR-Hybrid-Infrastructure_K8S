#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
OUTPUT_PATH="${1:-$ROOT_DIR/config/platform.env}"
FORCE_REGENERATE="${XDR_SOAR_FORCE_PLATFORM_ENV_REGEN:-0}"

if [ "${1:-}" = "--force" ]; then
  FORCE_REGENERATE=1
  OUTPUT_PATH="${2:-$ROOT_DIR/config/platform.env}"
fi

if [ -f "$OUTPUT_PATH" ] && [ "$FORCE_REGENERATE" != "1" ]; then
  echo "[$(date)] Reusing existing platform config at $OUTPUT_PATH"
  exit 0
fi

detect_public_ip() {
  if [ -n "${XDR_SOAR_PUBLIC_IP:-}" ]; then
    printf '%s\n' "$XDR_SOAR_PUBLIC_IP"
    return
  fi

  if command -v kubectl >/dev/null 2>&1; then
    local detected
    detected="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}' 2>/dev/null || true)"
    if [ -n "$detected" ]; then
      printf '%s\n' "$detected"
      return
    fi

    detected="$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null || true)"
    if [ -n "$detected" ]; then
      printf '%s\n' "$detected"
      return
    fi
  fi

  if command -v ipconfig >/dev/null 2>&1; then
    local iface
    iface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
    if [ -n "$iface" ]; then
      local mac_ip
      mac_ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
      if [ -n "$mac_ip" ]; then
        printf '%s\n' "$mac_ip"
        return
      fi
    fi
  fi

  printf '%s\n' "127.0.0.1"
}

is_ipv4() {
  local value="$1"
  [[ "$value" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

PUBLIC_IP="$(detect_public_ip)"
if is_ipv4 "$PUBLIC_IP"; then
  DEFAULT_BASE_DOMAIN="${PUBLIC_IP}.sslip.io"
else
  DEFAULT_BASE_DOMAIN="$PUBLIC_IP"
fi

XDR_SOAR_BASE_DOMAIN="${XDR_SOAR_BASE_DOMAIN:-$DEFAULT_BASE_DOMAIN}"
XDR_SOAR_INGRESS_CLASS="${XDR_SOAR_INGRESS_CLASS:-nginx}"
XDR_SOAR_TLS_MODE="${XDR_SOAR_TLS_MODE:-auto}"
XDR_SOAR_CERT_MANAGER_CLUSTER_ISSUER="${XDR_SOAR_CERT_MANAGER_CLUSTER_ISSUER:-xdr-soar-bootstrap-issuer}"
XDR_SOAR_ACME_EMAIL="${XDR_SOAR_ACME_EMAIL:-platform-ops@${XDR_SOAR_BASE_DOMAIN}}"
XDR_SOAR_ACME_SERVER="${XDR_SOAR_ACME_SERVER:-https://acme-v02.api.letsencrypt.org/directory}"
XDR_SOAR_TLS_SECRET_NAME="${XDR_SOAR_TLS_SECRET_NAME:-xdr-soar-platform-tls}"
XDR_SOAR_MQTT_TLS_SECRET_NAME="${XDR_SOAR_MQTT_TLS_SECRET_NAME:-xdr-soar-mqtt-tls}"
XDR_SOAR_MQTT_SERVICE_TYPE="${XDR_SOAR_MQTT_SERVICE_TYPE:-NodePort}"
XDR_SOAR_MQTT_NODE_PORT="${XDR_SOAR_MQTT_NODE_PORT:-30883}"
MQTT_HOSTNAME="${MQTT_BROKER_HOST:-mqtt.${XDR_SOAR_BASE_DOMAIN}}"

if [ "$XDR_SOAR_MQTT_SERVICE_TYPE" = "NodePort" ]; then
  MQTT_BROKER_PORT="${MQTT_BROKER_PORT:-$XDR_SOAR_MQTT_NODE_PORT}"
else
  MQTT_BROKER_PORT="${MQTT_BROKER_PORT:-8883}"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
umask 077
cat > "$OUTPUT_PATH" <<EOF
XDR_SOAR_BASE_DOMAIN=$XDR_SOAR_BASE_DOMAIN
XDR_SOAR_INGRESS_CLASS=$XDR_SOAR_INGRESS_CLASS
XDR_SOAR_TLS_MODE=$XDR_SOAR_TLS_MODE
XDR_SOAR_CERT_MANAGER_CLUSTER_ISSUER=$XDR_SOAR_CERT_MANAGER_CLUSTER_ISSUER
XDR_SOAR_ACME_EMAIL=$XDR_SOAR_ACME_EMAIL
XDR_SOAR_ACME_SERVER=$XDR_SOAR_ACME_SERVER
XDR_SOAR_TLS_SECRET_NAME=$XDR_SOAR_TLS_SECRET_NAME
XDR_SOAR_MQTT_TLS_SECRET_NAME=$XDR_SOAR_MQTT_TLS_SECRET_NAME
XDR_SOAR_MQTT_SERVICE_TYPE=$XDR_SOAR_MQTT_SERVICE_TYPE
XDR_SOAR_MQTT_NODE_PORT=$XDR_SOAR_MQTT_NODE_PORT
MQTT_BROKER_HOST=$MQTT_HOSTNAME
MQTT_BROKER_PORT=$MQTT_BROKER_PORT
MQTT_TOPIC=${MQTT_TOPIC:-/agent/update}
UPDATE_API_BASE_URL=${UPDATE_API_BASE_URL:-https://api.${XDR_SOAR_BASE_DOMAIN}/v1/firmware}
EOF

chmod 600 "$OUTPUT_PATH"
echo "[$(date)] Generated platform config at $OUTPUT_PATH"
