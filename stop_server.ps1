$appName = 'tencent-meeting-scheduler'
$found = $false

foreach ($port in 8080..8099) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 1
        if ($health.app -ne $appName) { continue }

        $process = Get-Process -Id $health.pid -ErrorAction Stop
        Stop-Process -Id $process.Id
        Write-Host "Stopped scheduler on port $port (PID $($process.Id))."
        $found = $true
    } catch {}
}

if (-not $found) {
    Write-Host 'No running scheduler service was found.'
}
