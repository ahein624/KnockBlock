# KnockBlock on-call sensor for Windows.
#
# Polls the ConsentStore registry keys — the same data Windows uses to show
# the camera/microphone tray indicators. An app with LastUsedTimeStop == 0
# is using the device right now. While anything is active this heartbeats
# the sign every 5s; the sign clears the status 15s after the last beat.
#
# Run at logon (adjust the path):
#   schtasks /Create /SC ONLOGON /TN KnockBlock /TR "powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Tools\knockblock-sensor.ps1"
#
# Configure via environment variables or by editing the two lines below.
$SignUrl = if ($env:KNOCKBLOCK_URL) { $env:KNOCKBLOCK_URL } else { "http://192.168.68.250:5000" }
$Token = if ($env:KNOCKBLOCK_TOKEN) { $env:KNOCKBLOCK_TOKEN } else { "" }

function Test-DeviceInUse([string]$Capability) {
    $root = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\$Capability"
    # Store apps live directly under the root; classic apps under NonPackaged.
    foreach ($key in @($root, "$root\NonPackaged")) {
        if (-not (Test-Path $key)) { continue }
        foreach ($app in Get-ChildItem $key -ErrorAction SilentlyContinue) {
            $props = Get-ItemProperty $app.PSPath -ErrorAction SilentlyContinue
            if ($null -ne $props -and $props.LastUsedTimeStop -eq 0) { return $true }
        }
    }
    return $false
}

function Send-OnCall([bool]$Active) {
    $headers = @{}
    if ($Token) { $headers["X-Api-Token"] = $Token }
    try {
        Invoke-RestMethod -Method Post -Uri "$SignUrl/api/oncall" -Headers $headers `
            -ContentType "application/json" -TimeoutSec 4 `
            -Body (@{ active = $Active } | ConvertTo-Json) | Out-Null
    } catch { }
}

$wasActive = $false
while ($true) {
    $active = (Test-DeviceInUse "microphone") -or (Test-DeviceInUse "webcam")
    if ($active) {
        Send-OnCall $true          # heartbeat while the call is live
    } elseif ($wasActive) {
        Send-OnCall $false         # single "call ended" as soon as we see it
    }
    $wasActive = $active
    Start-Sleep -Seconds 5
}
