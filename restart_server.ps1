Write-Host "Stopping service on port 5000..." -ForegroundColor Yellow

$processIds = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($processId in $processIds) {
    if ($processId) {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped process $processId" -ForegroundColor Green
    }
}

Start-Sleep -Seconds 1

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Starting backend: http://127.0.0.1:5000" -ForegroundColor Yellow
python .\backend\app.py
