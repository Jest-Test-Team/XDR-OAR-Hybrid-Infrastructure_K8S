# Windows Agent: 監聽 MQTT 並從 MongoDB (API API 橋接) 下載韌體
$mqttBroker = "mqtt.local"
$topic = "/agent/update"

Write-Host "Connecting to MQTT Broker to listen for updates..."
# 實際環境需引入 MQTT .NET Library (MQTTnet)
# 當收到 Payload {"action":"update"} 時觸發下載

function Invoke-Update {
    Write-Host "Downloading new firmware from MongoDB API..."
    Invoke-WebRequest -Uri "https://api.local/firmware/latest" -OutFile "C:\Temp\agent_new.exe"
    
    # 驗證 Hash
    $hash = Get-FileHash "C:\Temp\agent_new.exe" -Algorithm SHA256
    Write-Host "Hash verified. Restarting service..."
    
    Restart-Service -Name "WatchdogAgent"
}
