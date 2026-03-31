param(
    [string]$BundleRoot = $PSScriptRoot,
    [string]$InstallRoot = "C:\ProgramData\XDR\Updater",
    [string]$TaskName = "XDR-SOAR-Updater"
)

$ErrorActionPreference = "Stop"

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Install-CertificateIfMissing {
    param(
        [string]$CertificatePath,
        [string]$StoreLocation = "LocalMachine",
        [string]$StoreName = "Root"
    )

    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertificatePath)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($StoreName, $StoreLocation)
    $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    try {
        $existing = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
        if (-not $existing) {
            $store.Add($cert)
        }
    } finally {
        $store.Close()
    }
}

Ensure-Directory -Path $InstallRoot

$updaterScript = Join-Path $BundleRoot "mqtt-pull-updater.ps1"
$configFile = Join-Path $BundleRoot "updater-config.json"
$caFile = Join-Path $BundleRoot "ca.crt"

if (-not (Test-Path $updaterScript)) {
    throw "Missing updater script at $updaterScript"
}
if (-not (Test-Path $configFile)) {
    throw "Missing updater config at $configFile"
}
if (-not (Test-Path $caFile)) {
    throw "Missing CA certificate at $caFile"
}

$targetScript = Join-Path $InstallRoot "mqtt-pull-updater.ps1"
$targetConfig = Join-Path $InstallRoot "updater-config.json"
$targetCa = Join-Path $InstallRoot "ca.crt"

Copy-Item -Path $updaterScript -Destination $targetScript -Force
Copy-Item -Path $configFile -Destination $targetConfig -Force
Copy-Item -Path $caFile -Destination $targetCa -Force

Install-CertificateIfMissing -CertificatePath $targetCa

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$targetScript`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
$task = New-ScheduledTask -Action $action -Principal $principal -Trigger $trigger -Settings $settings

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed updater bundle to $InstallRoot and registered scheduled task $TaskName."
