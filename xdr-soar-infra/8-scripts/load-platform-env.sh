#!/bin/bash

set -euo pipefail

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "Source this file from another script instead of executing it directly." >&2
  exit 1
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PLATFORM_ENV="$ROOT_DIR/config/platform.env"
PLATFORM_ENV_EXAMPLE="$ROOT_DIR/config/platform.env.example"
SECRETS_ENV="${XDR_SOAR_SECRETS_ENV:-$ROOT_DIR/.generated/platform-secrets.env}"

if [ ! -f "$PLATFORM_ENV" ]; then
  "$SCRIPT_DIR/bootstrap-platform-config.sh" "$PLATFORM_ENV"
fi

load_env_file() {
  local env_file="$1"
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

if [ -f "$PLATFORM_ENV" ]; then
  load_env_file "$PLATFORM_ENV"
elif [ "${XDR_SOAR_REQUIRE_PLATFORM_ENV:-0}" = "1" ]; then
  echo "Missing $PLATFORM_ENV. Copy $PLATFORM_ENV_EXAMPLE and set the real deployment values." >&2
  return 1
else
  load_env_file "$PLATFORM_ENV_EXAMPLE"
fi

if [ ! -f "$SECRETS_ENV" ]; then
  "$SCRIPT_DIR/generate-platform-secrets.sh" "$SECRETS_ENV"
fi
load_env_file "$SECRETS_ENV"

: "${XDR_SOAR_BASE_DOMAIN:?Set XDR_SOAR_BASE_DOMAIN in $PLATFORM_ENV or $PLATFORM_ENV_EXAMPLE.}"
: "${XDR_SOAR_CERT_MANAGER_CLUSTER_ISSUER:?Set XDR_SOAR_CERT_MANAGER_CLUSTER_ISSUER in $PLATFORM_ENV or $PLATFORM_ENV_EXAMPLE.}"
: "${XDR_SOAR_ACME_EMAIL:?Set XDR_SOAR_ACME_EMAIL in $PLATFORM_ENV or $PLATFORM_ENV_EXAMPLE.}"

export XDR_SOAR_INGRESS_CLASS="${XDR_SOAR_INGRESS_CLASS:-nginx}"
export XDR_SOAR_TLS_MODE="${XDR_SOAR_TLS_MODE:-auto}"
export XDR_SOAR_ACME_SERVER="${XDR_SOAR_ACME_SERVER:-https://acme-v02.api.letsencrypt.org/directory}"
export XDR_SOAR_TLS_SECRET_NAME="${XDR_SOAR_TLS_SECRET_NAME:-xdr-soar-platform-tls}"
export XDR_SOAR_MQTT_TLS_SECRET_NAME="${XDR_SOAR_MQTT_TLS_SECRET_NAME:-xdr-soar-mqtt-tls}"
export XDR_SOAR_MQTT_SERVICE_TYPE="${XDR_SOAR_MQTT_SERVICE_TYPE:-NodePort}"
export XDR_SOAR_MQTT_NODE_PORT="${XDR_SOAR_MQTT_NODE_PORT:-30883}"

export XDR_SOAR_ADMIN_HOST="${XDR_SOAR_ADMIN_HOST:-admin.${XDR_SOAR_BASE_DOMAIN}}"
export XDR_SOAR_DASHBOARD_HOST="${XDR_SOAR_DASHBOARD_HOST:-dashboard.${XDR_SOAR_BASE_DOMAIN}}"
export XDR_SOAR_GRAFANA_HOST="${XDR_SOAR_GRAFANA_HOST:-grafana.${XDR_SOAR_BASE_DOMAIN}}"
export XDR_SOAR_STUDIO_HOST="${XDR_SOAR_STUDIO_HOST:-studio.${XDR_SOAR_BASE_DOMAIN}}"
export XDR_SOAR_SUPABASE_HOST="${XDR_SOAR_SUPABASE_HOST:-supabase.${XDR_SOAR_BASE_DOMAIN}}"
export XDR_SOAR_API_HOST="${XDR_SOAR_API_HOST:-api.${XDR_SOAR_BASE_DOMAIN}}"

export XDR_SOAR_API_EXTERNAL_URL="https://${XDR_SOAR_SUPABASE_HOST}"
export XDR_SOAR_GOTRUE_SITE_URL="https://${XDR_SOAR_DASHBOARD_HOST}"
export XDR_SOAR_GOTRUE_URI_ALLOW_LIST="https://${XDR_SOAR_DASHBOARD_HOST},https://${XDR_SOAR_ADMIN_HOST}"
export XDR_SOAR_DASHBOARD_PUBLIC_URL="https://${XDR_SOAR_STUDIO_HOST}"

export MQTT_BROKER_HOST="${MQTT_BROKER_HOST:-mqtt.${XDR_SOAR_BASE_DOMAIN}}"
if [ -n "${MQTT_BROKER_PORT:-}" ]; then
  export MQTT_BROKER_PORT
elif [ "$XDR_SOAR_MQTT_SERVICE_TYPE" = "NodePort" ]; then
  export MQTT_BROKER_PORT="$XDR_SOAR_MQTT_NODE_PORT"
else
  export MQTT_BROKER_PORT="8883"
fi
export MQTT_TOPIC="${MQTT_TOPIC:-/agent/update}"
export UPDATE_API_BASE_URL="${UPDATE_API_BASE_URL:-https://${XDR_SOAR_API_HOST}/v1/firmware}"

export XDR_SOAR_SUPABASE_DB_URL="postgres://${XDR_SOAR_SUPABASE_DB_USER}:${XDR_SOAR_SUPABASE_DB_PASSWORD}@supabase-db:5432/${XDR_SOAR_SUPABASE_DB_NAME}"
export XDR_SOAR_SUPABASE_DB_URL_SSLMODE_DISABLE="${XDR_SOAR_SUPABASE_DB_URL}?sslmode=disable"
