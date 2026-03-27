#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

docker build -q -f "$ROOT_DIR/apps/detection-engine/Dockerfile" -t custom-engine:v1.0.0 "$ROOT_DIR/apps/detection-engine"
docker build -q -f "$ROOT_DIR/apps/ml-training/Dockerfile" -t ml-training:v1.0.0 "$ROOT_DIR/apps/ml-training"
docker build -q -f "$ROOT_DIR/apps/yara-scanner/Dockerfile" -t custom-yara:v1.0.0 "$ROOT_DIR/apps/yara-scanner"
docker build -q -f "$ROOT_DIR/apps/admin-frontend/Dockerfile" -t admin-frontend:v1.0.0 "$ROOT_DIR/apps/admin-frontend"
docker build -q -f "$ROOT_DIR/apps/soar-dashboard/Dockerfile" -t soar-frontend:v1.0.0 "$ROOT_DIR/apps/soar-dashboard"

echo "Built internal application images."
