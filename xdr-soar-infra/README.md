# XDR/SOAR Infrastructure Repository

此目錄包含：

- `1-vmware-esxi/`: Terraform-managed VMware networking only
- `2-kubernetes-cluster/`: Cilium values template and install helper
- `3-k8s-network-policies/`: zero-trust namespace policies
- `4-data-layer/`: YAML-first data services, secrets, StatefulSets, and Supabase stack
- `5-security-engine/`: detection, retraining, Triton, and YARA manifests
- `6-frontend-ui/`: dashboard/admin Deployments, Services, and Ingress
- `7-windows-agents/`: Windows updater workflow
- `8-scripts/`: deploy and validation entrypoints
- `9-observability/`: Prometheus, Loki, Promtail, and Grafana
- `apps/`: Docker build contexts for internal application images

主要防禦目標：防止 VM Escape（Hypervisor 逃逸）與 VM Hopping（橫向移動）。
