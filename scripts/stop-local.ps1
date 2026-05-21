# Stop local Grocery Optimizer API/web processes safely.

$ErrorActionPreference = "Continue"

Write-Host "Stopping local API/web processes..." -ForegroundColor Yellow

$targets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.Name -in @("python.exe", "uvicorn.exe")) -and (
            ($_.CommandLine -match "grocery_optimizer\.api\.app:app" -and $_.CommandLine -match "--port\s+8000") -or
            ($_.CommandLine -match "http\.server" -and $_.CommandLine -match "\s8080\b" -and $_.CommandLine -match "--directory\s+web")
        )
    }

if (-not $targets) {
    Write-Host "[OK] No matching local API/web processes were running." -ForegroundColor Green
    exit 0
}

$stopped = @()
foreach ($proc in $targets) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        $stopped += $proc
    } catch {
        Write-Host "[WARN] Could not stop PID $($proc.ProcessId): $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if ($stopped.Count -gt 0) {
    Write-Host "[OK] Stopped $($stopped.Count) process(es):" -ForegroundColor Green
    foreach ($proc in $stopped) {
        Write-Host "  PID $($proc.ProcessId): $($proc.Name)" -ForegroundColor Green
    }
    exit 0
}

Write-Host "[WARN] No processes were stopped." -ForegroundColor Yellow
exit 1
