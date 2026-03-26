

# XDR/SOAR Hybrid Infrastructure (Project: Aegis-Watchdog)

本專案旨在建構一個高度隔離、自動化且具備機器學習偵測能力的 **擴展偵測與回應 (XDR)** 平台。架構結合了 **VMware ESXi** 的硬體虛擬化優勢與 **Kubernetes** 的微服務調度能力，專門用於處理 EDR Agent 測試、惡意程式分析及大規模安全事件編排。

-----

## 1\. 核心架構概述 (Architecture Overview)

系統分為三個主要層級，透過虛擬網路（vSwitch）與網路策略（Network Policy）進行邏輯與物理隔離：

  * **Endpoint Layer (Windows/macOS)**：獨立 OS 環境，運行待測 EDR Agent 與 Watchdog。
  * **Intelligence Layer (K8s)**：運行 9 個並行 ML 模型、YARA 掃描器與規則引擎。
  * **Data Hub (Middleware)**：由 Kafka、InfluxDB、MongoDB 與 Supabase 組成的數據中樞。

-----

## 2\. 安全隔離與硬化規範 (Security & Hardening)

為防止惡意軟體從測試 VM 逃逸（VM Escape）或橫向移動（VM Hopping），本 Repo 實作了以下防禦：

### 2.1 VMware 底層隔離 (VMX Hardening)

在 `1-vmware-esxi/` 配置中，所有 Windows 測試機必須關閉高風險的虛擬化通道：

  * **禁用 VMCI (Virtual Machine Communication Interface)**：切斷 VM 與 Hypervisor 的直接通訊。
  * **禁用剪貼簿與拖放 (Copy/Paste/DnD)**：防止跨邊界數據洩漏。
  * **MAC 欺騙防護**：vSwitch 拒絕所有偽造的 MAC 傳輸。

### 2.2 K8s 零信任網路 (Zero Trust Networking)

使用 **Cilium CNI (eBPF)** 實作三層防護：

1.  **Default Deny All**：所有 Namespace 預設禁止任何進出流量。
2.  **Micro-segmentation**：僅允許 MQTT Broker 接收來自特定 VLAN 100 (Windows) 的流量。
3.  **YARA Sandbox 隔離**：YARA 掃描器被限制為「唯讀存取 MongoDB 樣本庫」，並嚴禁任何外部（Egress）網際網路連線。

-----

## 3\. 組件詳細說明 (Component Breakdown)

| 類別 | 組件 | 技術棧 | 職責 |
| :--- | :--- | :--- | :--- |
| **數據存儲** | 時序資料庫 | InfluxDB 2.7 | 儲存從 Agent 回傳的高頻 Risk Scores。 |
| | 關聯資料庫 | Supabase (PG) | 儲存警報、設備資產與用戶操作日誌。 |
| | 文件存儲 | MongoDB 6.0 | 以 GridFS 儲存 `.pt` 模型與 Agent 韌體。 |
| **消息中心** | MQTT Broker | EMQX 5.0 | Agent 遙測數據接入與反向更新指令發送。 |
| | 數據匯流排 | Kafka | 高併發日誌削峰填谷，供偵測引擎消費。 |
| **偵測引擎** | ML 推論伺服器 | NVIDIA Triton | 並行運行 9 個不同維度的 ML 偵測模型。 |
| | 特徵掃描 | YARA Instance | 針對可疑二進位檔進行靜態特徵匹配。 |
| **監控系統** | 可觀測性 | Grafana 三件套 | Prometheus (指標)、Loki (日誌)、Grafana (面板)。 |

-----

## 4\. 自動化更新機制 (Pull-based Firmware Update)

本專案棄用傳統的推送（Push）模式，改採 **MQTT 觸發式拉取**：

1.  **CI 建置**：GitLab 編譯完成後，將 `agent.exe` 上傳至 MongoDB 並計算 SHA-256。
2.  **指令下達**：SOAR 後端發送 JSON 指令至 MQTT Topic `/agent/update`。
3.  **邊緣端執行**：
      * Windows Agent 接收到通知。
      * 透過 HTTPS 向 API 請求下載 MongoDB 內的二進位檔。
      * 驗證 Hash 值後自動執行重啟與更新。

-----

## 5\. 快速部署指南 (Deployment)

### 第一步：基礎設施準備

```bash
# 進入 VMware 配置目錄並初始化
cd 1-vmware-esxi/
terraform init && terraform apply
```

### 第二步：K8s 網路安全配置

```bash
# 部署 Cilium 並套用零信任策略
kubectl apply -f 2-kubernetes-cluster/cilium-values.yaml
kubectl apply -f 3-k8s-network-policies/
```

### 第三步：啟動核心微服務

```bash
# 使用整合腳本啟動資料層與引擎
cd 8-scripts/
bash deploy-all.sh
```

-----

## 6\. 基礎設施改良 (Infrastructure Improvements - 2026-03-26)

本專案已根據 `docs/repo-suggestions-todos-report.md` 完成以下核心改良：

1.  **冪等部署 (Idempotency)**：新增 `Namespace` 宣告，並重構 `deploy-all.sh` 以支援重複執行。
2.  **服務發現 (Service Discovery)**：為所有資料庫與引擎組件新增 `Service` 定義，消除對 Pod IP 的依賴。
3.  **網路策略強化 (NetPol Hardening)**：
    * 實作預設全阻斷 (Default Deny)。
    * 新增 DNS 解析白名單。
    * 建立精確的服務間通訊矩陣。
4.  **持久化與穩定性 (Persistence & Stability)**：
    * 為 MongoDB, Kafka, InfluxDB 啟用 `StatefulSet` 與 `volumeClaimTemplates`。
    * 新增容器資源限制 (CPU/Memory Requests & Limits)。
    * 導入 `readinessProbe` 與 `livenessProbe` 健康檢查。
5.  **安全硬化 (Security Hardening)**：
    * YARA 掃描器強制執行 `readOnlyRootFilesystem` 與能力裁減 (Capability Drop)。
    * 全面移除 `:latest` 標籤，改採固定版本鏡像。
    * 改良 Windows PowerShell Updater，導入 JSON Payload 驗證與 SHA-256 Hash 比對。

-----

## 7\. 維運與監控 (Maintenance)

  * **日誌查詢**：存取 Grafana 儀表板，過濾 `job="yara-scanner"` 檢視掃描歷史。
  * **模型訓練**：ML 訓練 Job 會在每天凌晨 2:00 自動從 Supabase 提取數據，並更新 MongoDB 中的 `.pt` 文件。
  * **警報通知**：當 InfluxDB 中的 Risk Score 超過 85 分時，Rule Engine 會自動推播警報至 SOAR Dashboard。

-----

## 7\. 資料來源與參考文獻 (Data Sources)

1.  **VMware 安全硬化基準**：[VMware vSphere 8 Security Hardening Guide](https://www.google.com/search?q=https://core.vmware.com/resource/vsphere-8-security-configuration-guide)
2.  **K8s 網路政策最佳實踐**：[Kubernetes Network Policies Best Practices](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
3.  **NVIDIA Triton 推論技術**：[Triton Inference Server Documentation](https://developer.nvidia.com/nvidia-triton-inference-server)
4.  **Cilium eBPF 隔離技術**：[Cilium Security Policy Reference](https://docs.cilium.io/en/stable/security/policy/)
5.  **MITRE ATT\&CK 框架**：[Matrix for Enterprise - T1222 (File and Directory Permissions Modification)](https://attack.mitre.org/techniques/T1222/)

-----

> **注意：** 在執行 YARA 掃描器測試前，請務必確認 `3-k8s-network-policies/02-isolate-yara.yaml` 已成功套用，以防止惡意樣本觸發反向連線。

