#!/bin/bash
echo "Deploying complete XDR/SOAR Infrastructure..."
kubectl create namespace xdr-soar
kubectl apply -f ../3-k8s-network-policies/
kubectl apply -f ../4-data-layer/mqtt/
kubectl apply -f ../4-data-layer/mongodb/
kubectl apply -f ../5-security-engine/
echo "Deployment applied. Check pods with 'kubectl get pods -n xdr-soar'"
