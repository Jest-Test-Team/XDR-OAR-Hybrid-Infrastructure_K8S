# XDR/SOAR Windows Agent: MQTT Pull-based Updater
# This implementation keeps a persistent MQTT-over-TLS connection to the broker
# and triggers the pull-based update workflow when a message arrives.

$DefaultConfigPath = Join-Path $env:ProgramData "XDR\config\updater-config.json"
$ConfigPath = [Environment]::GetEnvironmentVariable("XDR_UPDATER_CONFIG_PATH")
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = $DefaultConfigPath
}

$FileConfig = $null
if (Test-Path $ConfigPath) {
    $FileConfig = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
}

function Get-ConfigValue {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$EnvironmentVariable,
        [object]$Default = $null,
        [switch]$Required
    )

    $envValue = [Environment]::GetEnvironmentVariable($EnvironmentVariable)
    if ([string]::IsNullOrWhiteSpace($envValue)) {
        $envValue = [Environment]::GetEnvironmentVariable($EnvironmentVariable, [System.EnvironmentVariableTarget]::Machine)
    }
    if (-not [string]::IsNullOrWhiteSpace($envValue)) {
        return $envValue
    }

    if ($null -ne $FileConfig -and $FileConfig.PSObject.Properties.Name -contains $Name) {
        $fileValue = $FileConfig.$Name
        if ($null -ne $fileValue -and -not [string]::IsNullOrWhiteSpace([string]$fileValue)) {
            return [string]$fileValue
        }
    }

    if ($Required) {
        throw "Missing required updater setting '$Name'. Provide it in $ConfigPath or via environment variable $EnvironmentVariable."
    }

    return $Default
}

$Config = @{
    MqttBroker                  = Get-ConfigValue -Name "MqttBroker" -EnvironmentVariable "XDR_MQTT_BROKER" -Required
    MqttPort                    = [int](Get-ConfigValue -Name "MqttPort" -EnvironmentVariable "XDR_MQTT_PORT" -Default "8883")
    MqttTopic                   = Get-ConfigValue -Name "MqttTopic" -EnvironmentVariable "XDR_MQTT_TOPIC" -Default "/agent/update"
    MqttClientId                = Get-ConfigValue -Name "MqttClientId" -EnvironmentVariable "XDR_MQTT_CLIENT_ID" -Default ("watchdog-agent-" + $env:COMPUTERNAME)
    MqttKeepAliveSeconds        = [int](Get-ConfigValue -Name "MqttKeepAliveSeconds" -EnvironmentVariable "XDR_MQTT_KEEPALIVE_SECONDS" -Default "30")
    MqttUsername                = Get-ConfigValue -Name "MqttUsername" -EnvironmentVariable "XDR_MQTT_USERNAME" -Required
    MqttPassword                = Get-ConfigValue -Name "MqttPassword" -EnvironmentVariable "XDR_MQTT_PASSWORD" -Required
    ServerCertificateThumbprint = (Get-ConfigValue -Name "ServerCertificateThumbprint" -EnvironmentVariable "XDR_MQTT_SERVER_CERT_THUMBPRINT" -Required).ToUpperInvariant()
    UpdateApiUrl                = Get-ConfigValue -Name "UpdateApiUrl" -EnvironmentVariable "XDR_UPDATE_API_URL" -Required
    AgentServiceName            = Get-ConfigValue -Name "AgentServiceName" -EnvironmentVariable "XDR_AGENT_SERVICE_NAME" -Default "WatchdogAgent"
    AgentBinaryPath             = Get-ConfigValue -Name "AgentBinaryPath" -EnvironmentVariable "XDR_AGENT_BINARY_PATH" -Default "C:\Program Files\XDR\agent.exe"
    TempDir                     = Get-ConfigValue -Name "TempDir" -EnvironmentVariable "XDR_AGENT_TEMP_DIR" -Default "C:\Windows\Temp\XDR-Update"
    BackupDir                   = Get-ConfigValue -Name "BackupDir" -EnvironmentVariable "XDR_AGENT_BACKUP_DIR" -Default "C:\ProgramData\XDR\Backups"
    ReconnectDelaySeconds       = [int](Get-ConfigValue -Name "ReconnectDelaySeconds" -EnvironmentVariable "XDR_MQTT_RECONNECT_DELAY_SECONDS" -Default "5")
}

function Ensure-Directory {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

Ensure-Directory -Path $Config.TempDir
Ensure-Directory -Path $Config.BackupDir

function Test-UpdatePayload {
    param (
        [Parameter(Mandatory = $true)]
        [pscustomobject]$UpdateInfo
    )

    return -not [string]::IsNullOrWhiteSpace($UpdateInfo.version) -and
           -not [string]::IsNullOrWhiteSpace($UpdateInfo.sha256)
}

function Read-ExactBytes {
    param (
        [Parameter(Mandatory = $true)]
        [System.IO.Stream]$Stream,
        [Parameter(Mandatory = $true)]
        [int]$Length
    )

    $buffer = New-Object byte[] $Length
    $offset = 0
    while ($offset -lt $Length) {
        $read = $Stream.Read($buffer, $offset, $Length - $offset)
        if ($read -le 0) {
            throw "Unexpected end of MQTT stream."
        }
        $offset += $read
    }

    return $buffer
}

function ConvertTo-MqttStringBytes {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $valueBytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
    $buffer = New-Object System.IO.MemoryStream
    $lengthBytes = [System.BitConverter]::GetBytes([System.Net.IPAddress]::HostToNetworkOrder([int16]$valueBytes.Length))
    $buffer.Write($lengthBytes, 0, 2)
    $buffer.Write($valueBytes, 0, $valueBytes.Length)
    return $buffer.ToArray()
}

function ConvertTo-RemainingLengthBytes {
    param (
        [Parameter(Mandatory = $true)]
        [int]$Value
    )

    $bytes = New-Object System.Collections.Generic.List[byte]
    $remainingLength = $Value

    do {
        $encodedByte = $remainingLength % 128
        $remainingLength = [Math]::Floor($remainingLength / 128)
        if ($remainingLength -gt 0) {
            $encodedByte = $encodedByte -bor 0x80
        }
        $bytes.Add([byte]$encodedByte)
    } while ($remainingLength -gt 0)

    return $bytes.ToArray()
}

function Write-MqttPacket {
    param (
        [Parameter(Mandatory = $true)]
        [System.IO.Stream]$Stream,
        [Parameter(Mandatory = $true)]
        [byte]$Header,
        [byte[]]$Payload = @()
    )

    $buffer = New-Object System.IO.MemoryStream
    $buffer.WriteByte($Header)
    $remainingBytes = ConvertTo-RemainingLengthBytes -Value $Payload.Length
    $buffer.Write($remainingBytes, 0, $remainingBytes.Length)
    if ($Payload.Length -gt 0) {
        $buffer.Write($Payload, 0, $Payload.Length)
    }

    $packet = $buffer.ToArray()
    $Stream.Write($packet, 0, $packet.Length)
    $Stream.Flush()
}

function New-MqttConnectPayload {
    $payload = New-Object System.IO.MemoryStream
    $protocolBytes = ConvertTo-MqttStringBytes -Value "MQTT"
    $clientIdBytes = ConvertTo-MqttStringBytes -Value $Config.MqttClientId

    $payload.Write($protocolBytes, 0, $protocolBytes.Length)
    $payload.WriteByte(0x04)

    $connectFlags = 0x02
    if (-not [string]::IsNullOrWhiteSpace($Config.MqttUsername)) {
        $connectFlags = $connectFlags -bor 0x80
    }
    if (-not [string]::IsNullOrWhiteSpace($Config.MqttPassword)) {
        $connectFlags = $connectFlags -bor 0x40
    }
    $payload.WriteByte([byte]$connectFlags)

    $keepAliveBytes = [System.BitConverter]::GetBytes([System.Net.IPAddress]::HostToNetworkOrder([int16]$Config.MqttKeepAliveSeconds))
    $payload.Write($keepAliveBytes, 0, 2)
    $payload.Write($clientIdBytes, 0, $clientIdBytes.Length)

    if (-not [string]::IsNullOrWhiteSpace($Config.MqttUsername)) {
        $userBytes = ConvertTo-MqttStringBytes -Value $Config.MqttUsername
        $payload.Write($userBytes, 0, $userBytes.Length)
    }
    if (-not [string]::IsNullOrWhiteSpace($Config.MqttPassword)) {
        $passwordBytes = ConvertTo-MqttStringBytes -Value $Config.MqttPassword
        $payload.Write($passwordBytes, 0, $passwordBytes.Length)
    }

    return $payload.ToArray()
}

function Read-MqttPacket {
    param (
        [Parameter(Mandatory = $true)]
        [System.IO.Stream]$Stream
    )

    $firstByte = (Read-ExactBytes -Stream $Stream -Length 1)[0]
    $multiplier = 1
    $remainingLength = 0

    do {
        $encodedByte = (Read-ExactBytes -Stream $Stream -Length 1)[0]
        $remainingLength += ($encodedByte -band 127) * $multiplier
        $multiplier *= 128
    } while (($encodedByte -band 128) -ne 0)

    $payload = if ($remainingLength -gt 0) {
        Read-ExactBytes -Stream $Stream -Length $remainingLength
    } else {
        New-Object byte[] 0
    }

    return @{
        Header  = $firstByte
        Type    = ($firstByte -band 0xF0)
        Payload = $payload
    }
}

function Test-MqttServerCertificate {
    param (
        [Parameter(Mandatory = $true)]
        [System.Security.Cryptography.X509Certificates.X509Certificate]$Certificate,
        [Parameter(Mandatory = $true)]
        [System.Net.Security.SslPolicyErrors]$PolicyErrors
    )

    if (-not [string]::IsNullOrWhiteSpace($Config.ServerCertificateThumbprint)) {
        $expected = $Config.ServerCertificateThumbprint.ToUpperInvariant()
        $actual = $Certificate.GetCertHashString().ToUpperInvariant()
        return $actual -eq $expected
    }

    return $PolicyErrors -eq [System.Net.Security.SslPolicyErrors]::None
}

function New-MqttConnection {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect($Config.MqttBroker, $Config.MqttPort)

    $callback = {
        param($Sender, $Certificate, $Chain, $PolicyErrors)
        Test-MqttServerCertificate -Certificate $Certificate -PolicyErrors $PolicyErrors
    }

    $sslStream = New-Object System.Net.Security.SslStream($tcpClient.GetStream(), $false, $callback)
    $sslStream.AuthenticateAsClient(
        $Config.MqttBroker,
        $null,
        [System.Security.Authentication.SslProtocols]::Tls12,
        $false
    )
    $sslStream.ReadTimeout = 5000
    $sslStream.WriteTimeout = 5000

    Write-MqttPacket -Stream $sslStream -Header 0x10 -Payload (New-MqttConnectPayload)
    $connAck = Read-MqttPacket -Stream $sslStream
    if ($connAck.Type -ne 0x20 -or $connAck.Payload.Length -lt 2 -or $connAck.Payload[1] -ne 0) {
        throw "Broker rejected MQTT CONNECT."
    }

    $packetIdentifier = 1
    $topicBytes = ConvertTo-MqttStringBytes -Value $Config.MqttTopic
    $subscribePayload = New-Object System.IO.MemoryStream
    $packetIdBytes = [System.BitConverter]::GetBytes([System.Net.IPAddress]::HostToNetworkOrder([int16]$packetIdentifier))
    $subscribePayload.Write($packetIdBytes, 0, 2)
    $subscribePayload.Write($topicBytes, 0, $topicBytes.Length)
    $subscribePayload.WriteByte(0x00)
    Write-MqttPacket -Stream $sslStream -Header 0x82 -Payload $subscribePayload.ToArray()

    $subAck = Read-MqttPacket -Stream $sslStream
    if ($subAck.Type -ne 0x90) {
        throw "Broker did not acknowledge the SUBSCRIBE request."
    }

    return @{
        TcpClient = $tcpClient
        Stream    = $sslStream
    }
}

function Send-PubAck {
    param (
        [Parameter(Mandatory = $true)]
        [System.IO.Stream]$Stream,
        [Parameter(Mandatory = $true)]
        [int]$PacketIdentifier
    )

    $payload = [System.BitConverter]::GetBytes([System.Net.IPAddress]::HostToNetworkOrder([int16]$PacketIdentifier))
    Write-MqttPacket -Stream $Stream -Header 0x40 -Payload $payload
}

function Parse-PublishPacket {
    param (
        [Parameter(Mandatory = $true)]
        [hashtable]$Packet
    )

    $payload = $Packet.Payload
    $topicLength = ($payload[0] -shl 8) + $payload[1]
    $offset = 2
    $topic = [System.Text.Encoding]::UTF8.GetString($payload, $offset, $topicLength)
    $offset += $topicLength

    $qos = ($Packet.Header -band 0x06) -shr 1
    $packetId = $null
    if ($qos -gt 0) {
        $packetId = ($payload[$offset] -shl 8) + $payload[$offset + 1]
        $offset += 2
    }

    $message = [System.Text.Encoding]::UTF8.GetString($payload, $offset, $payload.Length - $offset)
    return @{
        Topic    = $topic
        Payload  = $message
        QoS      = $qos
        PacketId = $packetId
    }
}

function Invoke-Update {
    param (
        [Parameter(Mandatory = $true)]
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
        $DestFile = Join-Path $Config.TempDir "agent_$Version.exe"
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $DestFile -ErrorAction Stop

        $ActualHash = (Get-FileHash $DestFile -Algorithm SHA256).Hash.ToUpperInvariant()
        if ($ActualHash -ne $ExpectedHash) {
            throw "Hash mismatch. Expected $ExpectedHash but received $ActualHash"
        }

        Stop-Service -Name $Config.AgentServiceName -ErrorAction SilentlyContinue
        if (Test-Path $Config.AgentBinaryPath) {
            $BackupPath = Join-Path $Config.BackupDir "agent_$Version.bak.exe"
            Copy-Item $Config.AgentBinaryPath $BackupPath -Force
        }

        Move-Item $DestFile $Config.AgentBinaryPath -Force
        Start-Service -Name $Config.AgentServiceName
        Write-Host "[$(Get-Date)] Update successfully applied."
    }
    catch {
        Write-Error "Update failed: $($_.Exception.Message)"
    }
}

function Start-MqttListener {
    while ($true) {
        $connection = $null
        try {
            Write-Host "[$(Get-Date)] Connecting to $($Config.MqttBroker):$($Config.MqttPort)..."
            $connection = New-MqttConnection
            $lastActivity = Get-Date
            Write-Host "[$(Get-Date)] MQTT subscription active on topic $($Config.MqttTopic)"

            while ($true) {
                try {
                    $packet = Read-MqttPacket -Stream $connection.Stream
                    switch ($packet.Type) {
                        0x30 {
                            $message = Parse-PublishPacket -Packet $packet
                            if ($message.Topic -eq $Config.MqttTopic) {
                                Invoke-Update -PayloadJson $message.Payload
                            }
                            if ($message.QoS -eq 1 -and $null -ne $message.PacketId) {
                                Send-PubAck -Stream $connection.Stream -PacketIdentifier $message.PacketId
                            }
                            $lastActivity = Get-Date
                        }
                        0xD0 {
                            $lastActivity = Get-Date
                        }
                        default {
                            $lastActivity = Get-Date
                        }
                    }
                }
                catch [System.IO.IOException] {
                    if (((Get-Date) - $lastActivity).TotalSeconds -ge ($Config.MqttKeepAliveSeconds / 2)) {
                        Write-MqttPacket -Stream $connection.Stream -Header 0xC0 -Payload @()
                        $lastActivity = Get-Date
                        continue
                    }
                    throw
                }
                catch [System.TimeoutException] {
                    if (((Get-Date) - $lastActivity).TotalSeconds -ge ($Config.MqttKeepAliveSeconds / 2)) {
                        Write-MqttPacket -Stream $connection.Stream -Header 0xC0 -Payload @()
                        $lastActivity = Get-Date
                        continue
                    }
                    throw
                }
            }
        }
        catch {
            Write-Warning "[$(Get-Date)] MQTT listener error: $($_.Exception.Message)"
        }
        finally {
            if ($null -ne $connection) {
                if ($null -ne $connection.Stream) {
                    $connection.Stream.Dispose()
                }
                if ($null -ne $connection.TcpClient) {
                    $connection.TcpClient.Dispose()
                }
            }
        }

        Write-Host "[$(Get-Date)] Reconnecting in $($Config.ReconnectDelaySeconds) seconds..."
        Start-Sleep -Seconds $Config.ReconnectDelaySeconds
    }
}

Write-Host "XDR Agent Updater started. Monitoring $($Config.MqttTopic)..."
Start-MqttListener
