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
- `config/`: deployment-time domain/TLS settings and Windows updater config examples
- `IMAGE-PINNING.md`: verified image pin references and policy

主要防禦目標：防止 VM Escape（Hypervisor 逃逸）與 VM Hopping（橫向移動）。

部署流程目前會：

- 從 `config/platform.env` 載入正式網域、cert-manager 與 MQTT/API 端點設定
- 自動生成 `.generated/platform-secrets.env` 作為 bootstrap secrets
- 渲染 Secrets、Supabase URLs、Ingress/TLS 與 ClusterIssuer 模板後再套用
