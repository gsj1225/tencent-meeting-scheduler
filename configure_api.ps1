$ErrorActionPreference = 'Stop'

Write-Host 'Tencent Meeting API Configuration'
Write-Host 'Values will be stored in Windows user environment variables.'
Write-Host ''

$appId = Read-Host 'AppId'
$sdkId = Read-Host 'SdkId'
$secretId = Read-Host 'SecretId'
$secureSecret = Read-Host 'SecretKey' -AsSecureString
$secretPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
try {
    $secretKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($secretPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($secretPtr)
}

$values = @{
    TENCENT_MEETING_APP_ID = $appId.Trim()
    TENCENT_MEETING_SDK_ID = $sdkId.Trim()
    TENCENT_MEETING_SECRET_ID = $secretId.Trim()
    TENCENT_MEETING_SECRET_KEY = $secretKey.Trim()
}

if ($values.TENCENT_MEETING_APP_ID -notmatch '^\d+$' -or
    $values.TENCENT_MEETING_SDK_ID -notmatch '^\d+$') {
    Write-Host 'ERROR: AppId and SdkId must contain digits only.' -ForegroundColor Red
    exit 1
}
if ($values.TENCENT_MEETING_APP_ID.Length -gt $values.TENCENT_MEETING_SDK_ID.Length) {
    Write-Host 'ERROR: AppId and SdkId appear to be reversed. AppId is normally the shorter value.' -ForegroundColor Red
    exit 1
}

$missing = @($values.GetEnumerator() | Where-Object { -not $_.Value } | ForEach-Object { $_.Key })
if ($missing.Count -gt 0) {
    Write-Host ('ERROR: Empty values: ' + ($missing -join ', ')) -ForegroundColor Red
    exit 1
}

foreach ($item in $values.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($item.Key, $item.Value, 'User')
    $saved = [Environment]::GetEnvironmentVariable($item.Key, 'User')
    if ($saved -ne $item.Value) {
        throw "Failed to save $($item.Key)"
    }
}

Write-Host ''
Write-Host 'Configuration saved successfully.' -ForegroundColor Green
Write-Host 'Stop the old service, close its window, and start it again.'
