# XDR/SOAR Windows Agent: MQTT Pull-based Updater
# This script listens for update commands via MQTT and pulls new firmware from the Data Hub.

# Configuration
$Config = @{
    MqttBroker     = "mqtt.xdr-soar.local"
    MqttPort       = 8883
    MqttTopic      = "/agent/update"
    UpdateApiUrl   = "https://api.xdr-soar.local/v1/firmware"
    AgentServiceName = "WatchdogAgent"
    AgentBinaryPath = "C:\Program Files\XDR\agent.exe"
    TempDir        = "C:\Windows\Temp\XDR-Update"
    BackupDir      = "C:\ProgramData\XDR\Backups"
}

# Ensure Temp Directory exists
if (-not (Test-Path $Config.TempDir)) {
    New-Item -ItemType Directory -Force -Path $Config.TempDir
}

if (-not (Test-Path $Config.BackupDir)) {
    New-Item -ItemType Directory -Force -Path $Config.BackupDir
}

function Test-UpdatePayload {
    param (
        [Parameter(Mandatory=$true)]
        [pscustomobject]$UpdateInfo
    )

    return -not [string]::IsNullOrWhiteSpace($UpdateInfo.version) -and
           -not [string]::IsNullOrWhiteSpace($UpdateInfo.sha256)
}

function Invoke-Update {
    param (
        [Parameter(Mandatory=$true)]
        [string]$PayloadJson
    )

    try {
        $UpdateInfo = $PayloadJson | ConvertFrom-Json
        if (-not (Test-UpdatePayload -UpdateInfo $UpdateInfo)) {
            throw "Payload is missing required fields: version or sha256"
        }

        $Version = $UpdateInfo.version
        $ExpectedHash = $UpdateInfo.sha256.ToUpperInvariant()
        $DownloadUrl = "$($Config.UpdateApiUrl)/$Version"

        Write-Host "[$(Get-Date)] Starting update to version $Version"
        Write-Host "[$(Get-Date)] Expected SHA256: $ExpectedHash"

        $DestFile = Join-Path $Config.TempDir "agent_$Version.exe"
        
        # Download with TLS validation (in production, use certificate pinning)
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $DestFile -ErrorAction Stop

        # Verify Hash
        $ActualHash = (Get-FileHash $DestFile -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            Write-Error "Hash mismatch! Expected: $ExpectedHash, Got: $ActualHash"
            return
        }

        Write-Host "[$(Get-Date)] Hash verified. Applying update..."

        # Stopping service
        Stop-Service -Name $Config.AgentServiceName -ErrorAction SilentlyContinue

        if (Test-Path $Config.AgentBinaryPath) {
            $BackupPath = Join-Path $Config.BackupDir "agent_$Version.bak.exe"
            Copy-Item $Config.AgentBinaryPath $BackupPath -Force
        }

        Move-Item $DestFile $Config.AgentBinaryPath -Force

        # Restart service
        Start-Service -Name $Config.AgentServiceName
        
        Write-Host "[$(Get-Date)] Update successfully applied."
    }
    catch {
        Write-Error "Update failed: $($_.Exception.Message)"
    }
}

Write-Host "XDR Agent Updater started. Monitoring $($Config.MqttTopic)..."
# Note: Real implementation requires a .NET MQTT library like MQTTnet to handle the persistent connection.
# Example usage: Invoke-Update -PayloadJson '{"version": "1.2.3", "sha256": "A1B2C3D4..."}'
