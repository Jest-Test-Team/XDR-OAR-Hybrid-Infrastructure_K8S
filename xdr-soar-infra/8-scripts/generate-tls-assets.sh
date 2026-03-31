#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TLS_DIR="${1:-$ROOT_DIR/.generated/tls}"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-platform-env.sh"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate TLS assets." >&2
  exit 1
fi

mkdir -p "$TLS_DIR"
umask 077

generate_ca() {
  if [ -f "$TLS_DIR/ca.crt" ] && [ -f "$TLS_DIR/ca.key" ]; then
    return
  fi

  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$TLS_DIR/ca.key" \
    -out "$TLS_DIR/ca.crt" \
    -days 825 \
    -sha256 \
    -subj "/CN=XDR-SOAR Bootstrap Root CA" >/dev/null 2>&1
}

generate_leaf_cert() {
  local name="$1"
  shift
  local cfg_file="$TLS_DIR/${name}.cnf"
  local csr_file="$TLS_DIR/${name}.csr"
  local key_file="$TLS_DIR/${name}.key"
  local crt_file="$TLS_DIR/${name}.crt"
  local ext_index=1

  if [ -f "$key_file" ] && [ -f "$crt_file" ]; then
    return
  fi

  {
    echo "[req]"
    echo "distinguished_name = dn"
    echo "prompt = no"
    echo "req_extensions = v3_req"
    echo "[dn]"
    echo "CN = $1"
    echo "[v3_req]"
    echo "subjectAltName = @alt_names"
    echo "[alt_names]"
    for dns_name in "$@"; do
      echo "DNS.${ext_index} = ${dns_name}"
      ext_index=$((ext_index + 1))
    done
  } > "$cfg_file"

  openssl req -new -nodes -newkey rsa:2048 \
    -keyout "$key_file" \
    -out "$csr_file" \
    -config "$cfg_file" >/dev/null 2>&1

  openssl x509 -req \
    -in "$csr_file" \
    -CA "$TLS_DIR/ca.crt" \
    -CAkey "$TLS_DIR/ca.key" \
    -CAcreateserial \
    -out "$crt_file" \
    -days 825 \
    -sha256 \
    -extensions v3_req \
    -extfile "$cfg_file" >/dev/null 2>&1
}

generate_ca
generate_leaf_cert "platform" \
  "$XDR_SOAR_ADMIN_HOST" \
  "$XDR_SOAR_ADMIN_HOST" \
  "$XDR_SOAR_DASHBOARD_HOST" \
  "$XDR_SOAR_GRAFANA_HOST" \
  "$XDR_SOAR_STUDIO_HOST" \
  "$XDR_SOAR_SUPABASE_HOST" \
  "$XDR_SOAR_API_HOST"
generate_leaf_cert "mqtt" "$MQTT_BROKER_HOST" "$MQTT_BROKER_HOST"

echo "[$(date)] TLS assets are available under $TLS_DIR"
