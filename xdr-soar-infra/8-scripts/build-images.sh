#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

docker build -q -f "$ROOT_DIR/apps/detection-engine/Dockerfile" -t custom-engine:v1.0.0 "$ROOT_DIR/apps/detection-engine"
docker build -q -f "$ROOT_DIR/apps/firmware-api/Dockerfile" -t firmware-api:v1.0.0 "$ROOT_DIR/apps/firmware-api"
docker build -q -f "$ROOT_DIR/apps/ingest-gateway/Dockerfile" -t ingest-gateway:v1.0.0 "$ROOT_DIR/apps/ingest-gateway"
docker build -q -f "$ROOT_DIR/apps/ml-training/Dockerfile" -t ml-training:v1.0.0 "$ROOT_DIR/apps/ml-training"
docker build -q -f "$ROOT_DIR/apps/mq-bridge/Dockerfile" -t mq-bridge:v1.0.0 "$ROOT_DIR/apps/mq-bridge"
docker build -q -f "$ROOT_DIR/apps/stream-processor/Dockerfile" -t stream-processor:v1.0.0 "$ROOT_DIR/apps/stream-processor"
docker build -q -f "$ROOT_DIR/apps/yara-scanner/Dockerfile" -t custom-yara:v1.0.0 "$ROOT_DIR/apps/yara-scanner"
docker build -q -f "$ROOT_DIR/apps/admin-frontend/Dockerfile" -t admin-frontend:v1.0.0 "$ROOT_DIR/apps/admin-frontend"
docker build -q -f "$ROOT_DIR/apps/command-dispatcher/Dockerfile" -t command-dispatcher:v1.0.0 "$ROOT_DIR/apps/command-dispatcher"
docker build -q -f "$ROOT_DIR/apps/soar-api/Dockerfile" -t soar-api:v1.0.0 "$ROOT_DIR/apps/soar-api"
docker build -q -f "$ROOT_DIR/apps/soar-dashboard/Dockerfile" -t soar-frontend:v1.0.0 "$ROOT_DIR/apps/soar-dashboard"

echo "Built internal application images."
