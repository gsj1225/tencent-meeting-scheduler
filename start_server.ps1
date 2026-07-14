$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appName = 'tencent-meeting-scheduler'
$ports = 8080..8099
$credentialNames = @(
    'TENCENT_MEETING_APP_ID',
    'TENCENT_MEETING_SDK_ID',
    'TENCENT_MEETING_SECRET_ID',
    'TENCENT_MEETING_SECRET_KEY'
)

# Explorer may retain an old environment snapshot. Read current user values directly.
foreach ($name in $credentialNames) {
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

Write-Host 'Tencent Meeting Scheduler'
Write-Host 'Checking ports...'

$usedPorts = @(
    [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        ForEach-Object { $_.Port }
)

foreach ($port in $ports) {
    if ($usedPorts -notcontains $port) { continue }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 1
        if ($health.app -eq $appName) {
            Write-Host "Service is already running on port $port."
            Start-Process "http://localhost:$port"
            exit 0
        }
    } catch {}
}

$port = $ports | Where-Object { $usedPorts -notcontains $_ } | Select-Object -First 1
if (-not $port) {
    Write-Host 'ERROR: Ports 8080-8099 are all in use.' -ForegroundColor Red
    exit 1
}

if ($port -ne 8080) {
    Write-Host "Port 8080 is in use. Using port $port instead." -ForegroundColor Yellow
}
if (-not $env:SCHEDULE_APP_PASSWORD) {
    Write-Host 'Login protection is disabled (local use only).' -ForegroundColor Yellow
}
if ($credentialNames | Where-Object { -not (Get-Item -Path "Env:$_" -ErrorAction SilentlyContinue).Value }) {
    Write-Host 'Tencent Meeting API variables are incomplete.' -ForegroundColor Yellow
}

$env:SCHEDULE_PORT = [string]$port
$env:SCHEDULE_OPEN_BROWSER = '1'
Set-Location $projectDir
Write-Host "Starting http://localhost:$port"
& python server.py
exit $LASTEXITCODE
