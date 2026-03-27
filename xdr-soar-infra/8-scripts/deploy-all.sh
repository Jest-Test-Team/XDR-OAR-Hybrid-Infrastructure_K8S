#!/bin/bash
# XDR/SOAR Infrastructure: Deployment Script (Idempotent)
# 
# This script deploys the entire stack in the correct dependency order.

# Exit on error and undefined variables.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

echo "[$(date)] Starting XDR/SOAR Infrastructure deployment..."

# 1. Create Namespace (Idempotent)
echo "[$(date)] Applying Namespace..."
kubectl apply -f "$SCRIPT_DIR/../2-kubernetes-cluster/00-namespace.yaml"

# 2. Network Policies
echo "[$(date)] Applying Network Policies..."
kubectl apply -f "$SCRIPT_DIR/../3-k8s-network-policies/"

# 3. Data Layer (Secrets, Services, StatefulSets, then stateless dependencies)
echo "[$(date)] Applying Data Layer (Kafka, MongoDB, InfluxDB, etc.)..."
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/00-secrets.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/services.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/mongodb/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/influxdb/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/kafka/statefulset.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/mqtt/deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/redis/deployment.yaml"
kubectl apply -f "$SCRIPT_DIR/../4-data-layer/supabase/"

# 4. Security Engine (Inference servers, Rules, Scanners)
echo "[$(date)] Applying Security Engine..."
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/services.yaml"
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/model-repository-pvc.yaml"
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/combined-engine.yaml"
kubectl apply -f "$SCRIPT_DIR/../5-security-engine/firmware-api.yaml"

# 5. Frontend UI
echo "[$(date)] Applying Frontend UI..."
kubectl apply -f "$SCRIPT_DIR/../6-frontend-ui/combined-frontend.yaml"
kubectl apply -f "$SCRIPT_DIR/../6-frontend-ui/ingress.yaml"

# 6. Observability
echo "[$(date)] Applying Observability Stack..."
kubectl apply -f "$SCRIPT_DIR/../9-observability/"

echo "[$(date)] Deployment finished. Run 'kubectl get pods -n xdr-soar' to monitor status."
