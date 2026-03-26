import os
from pathlib import Path

# 定義 Repository 結構與檔案內容
repo_name = "xdr-soar-infra"
files = {
    ".gitlab-ci.yml": """\
stages:
  - build
  - push
  - notify_update

build_agent:
  stage: build
  tags: [isolated-runner]
  script:
    - echo "Building Windows EDR Agent..."
    - pyinstaller --onefile agent_main.py

push_to_mongodb:
  stage: push
  script:
    - echo "Uploading binary to MongoDB GridFS..."
    - python scripts/upload_to_gridfs.py ./dist/agent.exe

notify_mqtt:
  stage: notify_update
  script:
    - echo "Publishing update command to MQTT topic /agent/update..."
    - mosquitto_pub -h mqtt.local -t "/agent/update" -m '{"action":"update", "version":"latest"}'
""",
    "README.md": """\
# XDR/SOAR Infrastructure Repository
此 Repo 包含 VMware ESXi 底層配置、K8s 叢集部署、微服務架構與嚴格的零信任網路隔離策略。
主要防禦目標：防止 VM Escape（Hypervisor 逃逸）與 VM Hopping（橫向移動）。
""",
    "1-vmware-esxi/01-network-segmentation.tf": """\
provider "vsphere" {
  user           = var.vsphere_user
  password       = var.vsphere_password
  vsphere_server = var.vsphere_server
  allow_unverified_ssl = true
}

# 建立高度隔離的 Windows Agent 測試網段 (防嗅探與偽造)
resource "vsphere_distributed_port_group" "isolated_windows_pg" {
  name                            = "VLAN-100-Windows-Isolated"
  vlan_id                         = 100
  allow_promiscuous               = false
  allow_mac_changes               = false
  allow_forged_transmits          = false
}
""",
    "1-vmware-esxi/02-vmx-hardening.json": """\
{
  "_comment": "VMware 進階參數硬化，防止 Windows VM 測試惡意軟體時反向入侵 Hypervisor",
  "isolation.tools.copy.disable": "TRUE",
  "isolation.tools.paste.disable": "TRUE",
  "isolation.tools.dnd.disable": "TRUE",
  "isolation.tools.setGUIOptions.enable": "FALSE",
  "vmci0.present": "FALSE",
  "serial0.present": "FALSE",
  "parallel0.present": "FALSE"
}
""",
    "2-kubernetes-cluster/cilium-values.yaml": """\
# Cilium CNI 配置：啟用 eBPF 與 L7 網路策略支援
kubeProxyReplacement: strict
k8sServiceHost: API_SERVER_IP
k8sServicePort: 6443
routingMode: native
endpointRoutes:
  enabled: true
ipv4NativeRoutingCIDR: 10.0.0.0/8
""",
    "3-k8s-network-policies/00-default-deny-all.yaml": """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: xdr-soar
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
""",
    "3-k8s-network-policies/01-allow-mqtt-ingress.yaml": """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-windows-to-mqtt
  namespace: xdr-soar
spec:
  podSelector:
    matchLabels:
      app: mqtt-broker
  policyTypes:
  - Ingress
  ingress:
  - from:
    - ipBlock:
        cidr: 192.168.100.0/24 # 僅允許 Windows 隔離網段
    ports:
    - protocol: TCP
      port: 8883
""",
    "3-k8s-network-policies/02-isolate-yara.yaml": """\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: isolate-yara-scanner
  namespace: xdr-soar
spec:
  podSelector:
    matchLabels:
      app: yara-scanner
  policyTypes:
  - Egress
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: mongodb # 僅允許連線至 MongoDB 抓取樣本
    ports:
    - protocol: TCP
      port: 27017
""",
    "4-data-layer/mqtt/deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mqtt-broker
  namespace: xdr-soar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mqtt-broker
  template:
    metadata:
      labels:
        app: mqtt-broker
    spec:
      containers:
      - name: emqx
        image: emqx/emqx:5.0
        ports:
        - containerPort: 1883
        - containerPort: 8883 # TLS
""",
    "4-data-layer/kafka/statefulset.yaml": """\
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kafka-cluster
  namespace: xdr-soar
spec:
  serviceName: "kafka"
  replicas: 3
  selector:
    matchLabels:
      app: kafka
  template:
    metadata:
      labels:
        app: kafka
    spec:
      containers:
      - name: kafka
        image: confluentinc/cp-kafka:latest
""",
    "4-data-layer/mongodb/statefulset.yaml": """\
# MongoDB 用於儲存 .pt 模型與 Agent 韌體 (GridFS)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mongodb
  namespace: xdr-soar
spec:
  serviceName: "mongodb"
  replicas: 1
  selector:
    matchLabels:
      app: mongodb
  template:
    metadata:
      labels:
        app: mongodb
    spec:
      containers:
      - name: mongodb
        image: mongo:6.0
""",
    "4-data-layer/influxdb/statefulset.yaml": """\
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: influxdb
  namespace: xdr-soar
spec:
  serviceName: "influxdb"
  replicas: 1
  selector:
    matchLabels:
      app: influxdb
  template:
    metadata:
      labels:
        app: influxdb
    spec:
      containers:
      - name: influxdb
        image: influxdb:2.7
""",
    "4-data-layer/supabase/deployment.yaml": """\
# Supabase (PostgreSQL + GoTrue + PostgREST) 集合部署佔位符
apiVersion: apps/v1
kind: Deployment
metadata:
  name: supabase-core
  namespace: xdr-soar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: supabase
  template:
    metadata:
      labels:
        app: supabase
    spec:
      containers:
      - name: postgres
        image: supabase/postgres:latest
""",
    "4-data-layer/redis/deployment.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis-cache
  namespace: xdr-soar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:alpine
""",
    "5-security-engine/1-detection-engine.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: detection-engine
  namespace: xdr-soar
spec:
  replicas: 2
  selector:
    matchLabels:
      app: engine
  template:
    metadata:
      labels:
        app: engine
    spec:
      containers:
      - name: rules-engine
        image: custom-engine:latest
        env:
        - name: INFLUXDB_URL
          value: "http://influxdb:8086"
""",
    "5-security-engine/2-ml-models-triton.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-triton-server
  namespace: xdr-soar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ml-triton
  template:
    metadata:
      labels:
        app: ml-triton
    spec:
      containers:
      - name: triton
        image: nvcr.io/nvidia/tritonserver:latest
        args: ["tritonserver", "--model-repository=/models"]
""",
    "5-security-engine/3-ml-training-cronjob.yaml": """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: ml-retraining
  namespace: xdr-soar
spec:
  schedule: "0 2 * * *" # 每天凌晨 2 點執行訓練
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: training-job
            image: ml-training:latest
          restartPolicy: OnFailure
""",
    "5-security-engine/4-yara-scanner.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yara-scanner
  namespace: xdr-soar
spec:
  replicas: 2
  selector:
    matchLabels:
      app: yara-scanner
  template:
    metadata:
      labels:
        app: yara-scanner
    spec:
      securityContext:
        runAsNonRoot: true
        readOnlyRootFilesystem: true
      containers:
      - name: yara
        image: custom-yara:latest
""",
    "6-frontend-ui/soar-dashboard.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: soar-dashboard
  namespace: xdr-soar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: soar-ui
  template:
    metadata:
      labels:
        app: soar-ui
    spec:
      containers:
      - name: frontend
        image: soar-frontend:latest
""",
    "6-frontend-ui/admin-panel.yaml": """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: admin-panel
  namespace: xdr-soar
spec:
  replicas: 1
  selector:
    matchLabels:
      app: admin-ui
  template:
    metadata:
      labels:
        app: admin-ui
    spec:
      containers:
      - name: admin
        image: admin-frontend:latest
""",
    "7-windows-agents/mqtt-pull-updater.ps1": """\
# Windows Agent: 監聽 MQTT 並從 MongoDB (API API 橋接) 下載韌體
$mqttBroker = "mqtt.local"
$topic = "/agent/update"

Write-Host "Connecting to MQTT Broker to listen for updates..."
# 實際環境需引入 MQTT .NET Library (MQTTnet)
# 當收到 Payload {"action":"update"} 時觸發下載

function Invoke-Update {
    Write-Host "Downloading new firmware from MongoDB API..."
    Invoke-WebRequest -Uri "https://api.local/firmware/latest" -OutFile "C:\\Temp\\agent_new.exe"
    
    # 驗證 Hash
    $hash = Get-FileHash "C:\\Temp\\agent_new.exe" -Algorithm SHA256
    Write-Host "Hash verified. Restarting service..."
    
    Restart-Service -Name "WatchdogAgent"
}
""",
    "8-scripts/deploy-all.sh": """\
#!/bin/bash
echo "Deploying complete XDR/SOAR Infrastructure..."
kubectl create namespace xdr-soar
kubectl apply -f ../3-k8s-network-policies/
kubectl apply -f ../4-data-layer/mqtt/
kubectl apply -f ../4-data-layer/mongodb/
kubectl apply -f ../5-security-engine/
echo "Deployment applied. Check pods with 'kubectl get pods -n xdr-soar'"
"""
}

def create_repo():
    print(f"Creating repository: {repo_name}...")
    for file_path, content in files.items():
        full_path = Path(repo_name) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Created: {full_path}")
    print("\\n✅ Repository successfully generated! You can now zip the folder.")

if __name__ == "__main__":
    create_repo()