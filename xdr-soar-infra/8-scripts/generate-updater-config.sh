#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
OUTPUT_PATH="${1:-$ROOT_DIR/config/updater-config.json}"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/load-platform-env.sh"
"$SCRIPT_DIR/generate-tls-assets.sh" >/dev/null

MQTT_CERT_PATH="$ROOT_DIR/.generated/tls/mqtt.crt"
MQTT_THUMBPRINT="$(openssl x509 -in "$MQTT_CERT_PATH" -noout -fingerprint -sha1 | awk -F= '{print $2}' | tr -d ':')"

mkdir -p "$(dirname "$OUTPUT_PATH")"
umask 077
cat > "$OUTPUT_PATH" <<EOF
{
  "MqttBroker": "${MQTT_BROKER_HOST}",
  "MqttPort": ${MQTT_BROKER_PORT},
  "MqttTopic": "${MQTT_TOPIC}",
  "MqttKeepAliveSeconds": 30,
  "MqttUsername": "${XDR_SOAR_MQTT_USERNAME}",
  "MqttPassword": "${XDR_SOAR_MQTT_PASSWORD}",
  "ServerCertificateThumbprint": "${MQTT_THUMBPRINT}",
  "UpdateApiUrl": "${UPDATE_API_BASE_URL}",
  "AgentServiceName": "WatchdogAgent",
  "AgentBinaryPath": "C:\\\\Program Files\\\\XDR\\\\agent.exe",
  "TempDir": "C:\\\\Windows\\\\Temp\\\\XDR-Update",
  "BackupDir": "C:\\\\ProgramData\\\\XDR\\\\Backups",
  "ReconnectDelaySeconds": 5
}
EOF

chmod 600 "$OUTPUT_PATH"
echo "[$(date)] Generated updater config at $OUTPUT_PATH"
