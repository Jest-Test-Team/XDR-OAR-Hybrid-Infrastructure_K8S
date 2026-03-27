#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
OUTPUT_PATH="${1:-$ROOT_DIR/.generated/platform-secrets.env}"
FORCE_REGENERATE="${XDR_SOAR_FORCE_SECRET_REGEN:-0}"

if [ "${1:-}" = "--force" ]; then
  FORCE_REGENERATE=1
  OUTPUT_PATH="${2:-$ROOT_DIR/.generated/platform-secrets.env}"
fi

if [ -f "$OUTPUT_PATH" ] && [ "$FORCE_REGENERATE" != "1" ]; then
  echo "[$(date)] Reusing existing secret bundle at $OUTPUT_PATH"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate bootstrap secrets." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to generate Supabase JWT keys." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
umask 077

random_hex() {
  openssl rand -hex "$1"
}

random_urlsafe() {
  openssl rand -base64 "$1" | tr -d '\n=' | tr '/+' '_-'
}

make_supabase_jwt() {
  SUPABASE_JWT_SECRET="$1" SUPABASE_JWT_ROLE="$2" python3 - <<'PY'
import base64
import hashlib
import hmac
import json
import os
import time

def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

secret = os.environ["SUPABASE_JWT_SECRET"].encode("utf-8")
role = os.environ["SUPABASE_JWT_ROLE"]
issued_at = int(time.time())
payload = {
    "aud": "authenticated",
    "exp": issued_at + 31536000,
    "iat": issued_at,
    "iss": "xdr-soar-bootstrap",
    "role": role,
    "sub": role,
}
header = {"alg": "HS256", "typ": "JWT"}
header_part = b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
payload_part = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
signing_input = f"{header_part}.{payload_part}".encode("ascii")
signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
print(f"{header_part}.{payload_part}.{b64url(signature)}")
PY
}

XDR_SOAR_SUPABASE_JWT_SECRET="$(random_urlsafe 48)"
XDR_SOAR_SUPABASE_ANON_KEY="$(make_supabase_jwt "$XDR_SOAR_SUPABASE_JWT_SECRET" "anon")"
XDR_SOAR_SUPABASE_SERVICE_ROLE_KEY="$(make_supabase_jwt "$XDR_SOAR_SUPABASE_JWT_SECRET" "service_role")"
XDR_SOAR_SUPABASE_DASHBOARD_USERNAME="${XDR_SOAR_SUPABASE_DASHBOARD_USERNAME:-platform-admin@${XDR_SOAR_BASE_DOMAIN:-example.invalid}}"

: > "$OUTPUT_PATH"

write_kv() {
  printf '%s=%q\n' "$1" "$2" >> "$OUTPUT_PATH"
}

write_kv "XDR_SOAR_MONGODB_ROOT_USERNAME" "xdradmin"
write_kv "XDR_SOAR_MONGODB_ROOT_PASSWORD" "$(random_hex 24)"
write_kv "XDR_SOAR_INFLUXDB_USERNAME" "xdradmin"
write_kv "XDR_SOAR_INFLUXDB_PASSWORD" "$(random_hex 24)"
write_kv "XDR_SOAR_INFLUXDB_ORG" "xdr-soar"
write_kv "XDR_SOAR_INFLUXDB_BUCKET" "risk-scores"
write_kv "XDR_SOAR_INFLUXDB_ADMIN_TOKEN" "$(random_urlsafe 48)"
write_kv "XDR_SOAR_SUPABASE_DB_USER" "postgres"
write_kv "XDR_SOAR_SUPABASE_DB_PASSWORD" "$(random_hex 24)"
write_kv "XDR_SOAR_SUPABASE_DB_NAME" "postgres"
write_kv "XDR_SOAR_SUPABASE_JWT_SECRET" "$XDR_SOAR_SUPABASE_JWT_SECRET"
write_kv "XDR_SOAR_SUPABASE_ANON_KEY" "$XDR_SOAR_SUPABASE_ANON_KEY"
write_kv "XDR_SOAR_SUPABASE_SERVICE_ROLE_KEY" "$XDR_SOAR_SUPABASE_SERVICE_ROLE_KEY"
write_kv "XDR_SOAR_SUPABASE_DASHBOARD_USERNAME" "$XDR_SOAR_SUPABASE_DASHBOARD_USERNAME"
write_kv "XDR_SOAR_SUPABASE_DASHBOARD_PASSWORD" "$(random_hex 18)"
write_kv "XDR_SOAR_GRAFANA_ADMIN_USER" "admin"
write_kv "XDR_SOAR_GRAFANA_ADMIN_PASSWORD" "$(random_hex 18)"
write_kv "XDR_SOAR_MQTT_USERNAME" "agent-updater"
write_kv "XDR_SOAR_MQTT_PASSWORD" "$(random_hex 18)"

chmod 600 "$OUTPUT_PATH"
echo "[$(date)] Generated bootstrap secrets at $OUTPUT_PATH"
