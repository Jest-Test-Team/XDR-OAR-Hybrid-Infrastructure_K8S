flowchart TB
    subgraph External["外部/開發環境"]
        GitLab["GitLab CI/CD\n(Isolated Runner)"]
    end

    subgraph ESXi["Server A: VMware ESXi 主機"]
        
        subgraph vSwitch["虛擬網路邊界 (vSwitch / Micro-segmentation)"]
            direction LR
            VLAN20["K8s App Network\n(VLAN 20)"]
            VLAN100["Isolated Testing Net\n(VLAN 100 / Anti-MAC Spoofing)"]
        end

        subgraph K8s["VM: Kubernetes 叢集 (Linux)"]
            subgraph NS["Namespace: xdr-soar\n[套用 Network Policy: Default Deny All]"]
                
                subgraph UI["UI 與人類操作層"]
                    UI_SOAR["SOAR Dashboard"]
                    UI_Admin["Admin Panel"]
                end

                subgraph Engine["核心運算與掃描引擎"]
                    Det_Eng["Detection Engine\n(Rules / C++ or Go)"]
                    ML_Triton["Triton ML Server\n(9 Models Serving)"]
                    ML_Train["ML Retraining\n(CronJob)"]
                    Yara["YARA Scanner\n[嚴格限制 Egress]"]
                end

                subgraph DataMsg["資料持久化與訊息佇列"]
                    MQTT["MQTT Broker\n(Ingress: Port 8883 TLS)"]
                    Kafka{"Kafka Cluster"}
                    Redis(("Redis Cache"))
                    Mongo[("MongoDB\n(GridFS: .pt / firmware)")]
                    Influx[("InfluxDB\n(Risk Scores)")]
                    Supa[["Supabase\n(PostgreSQL/Auth)"]]
                end
            end
        end

        subgraph WinVM["VM: Windows EDR 測試節點"]
            direction TB
            Hardening["[VMX Hardening: VMCI Disabled]"]
            Agent["EDR Agent / Watchdog"]
            Updater["PowerShell Updater\n(Listen MQTT / Pull API)"]
        end
        
    end

    %% 網卡掛載與底層防火牆
    K8s --- VLAN20
    WinVM --- VLAN100
    VLAN100 -. "vSphere/NSX 防火牆限制" .- VLAN20

    %% CI/CD 韌體與模型派發流
    GitLab -- "1. 編譯並上傳 .exe" --> Mongo
    ML_Train -- "產出並儲存 .pt 模型" --> Mongo
    
    %% 自動化 Pull-based 更新流
    UI_Admin -- "2. 下達更新指令" --> MQTT
    Updater -- "3. 訂閱 /agent/update" --> MQTT
    Updater -- "4. 透過 API 拉取韌體" --> Mongo
    Updater -- "5. 替換 Agent" --> Agent

    %% EDR 遙測與偵測流
    Agent -- "高頻 Telemetry" --> MQTT
    MQTT -- "轉發" --> Kafka
    Kafka -- "串流分析" --> Det_Eng & ML_Triton
    ML_Triton -- "讀取最新 .pt" --> Mongo
    
    %% 引擎處置流
    Det_Eng -- "寫入/查詢趨勢" --> Influx
    Det_Eng -- "寫入關聯告警" --> Supa
    
    %% YARA 動態分析流
    Yara -- "僅允許讀取樣本" --> Mongo
    Yara -- "回傳掃描結果" --> Kafka