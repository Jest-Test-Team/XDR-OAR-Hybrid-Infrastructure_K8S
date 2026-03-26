#!/bin/bash
# XDR/SOAR Infrastructure: Deployment Script (Idempotent)
# 
# This script deploys the entire stack in the correct dependency order.

# Exit on error
set -e

echo "[$(date)] Starting XDR/SOAR Infrastructure deployment..."

# 1. Create Namespace (Idempotent)
echo "[$(date)] Applying Namespace..."
kubectl apply -f ../2-kubernetes-cluster/00-namespace.yaml

# 2. Network Policies
echo "[$(date)] Applying Network Policies..."
kubectl apply -f ../3-k8s-network-policies/

# 3. Data Layer (Persistent Storage first, then Services, then Deployments)
echo "[$(date)] Applying Data Layer (Kafka, MongoDB, InfluxDB, etc.)..."
# Note: StatefulSets include VolumeClaimTemplates which will trigger PV/PVC creation
kubectl apply -f ../4-data-layer/mongodb/statefulset.yaml
kubectl apply -f ../4-data-layer/influxdb/statefulset.yaml
kubectl apply -f ../4-data-layer/kafka/statefulset.yaml
kubectl apply -f ../4-data-layer/services.yaml
kubectl apply -f ../4-data-layer/combined-deployments.yaml

# 4. Security Engine (Inference servers, Rules, Scanners)
echo "[$(date)] Applying Security Engine..."
kubectl apply -f ../5-security-engine/services.yaml
kubectl apply -f ../5-security-engine/combined-engine.yaml

# 5. Frontend UI
echo "[$(date)] Applying Frontend UI..."
kubectl apply -f ../6-frontend-ui/combined-frontend.yaml

echo "[$(date)] Deployment finished. Run 'kubectl get pods -n xdr-soar' to monitor status."
