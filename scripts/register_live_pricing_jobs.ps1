param(
    [string]$TaskName = "GroceryOptimizer-LivePricingJobs",
    [int]$IntervalMinutes = 30,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RunnerScript = Join-Path $ProjectRoot "scripts\run_live_pricing_jobs.py"

if ($Remove) {
    schtasks /Delete /TN $TaskName /F | Out-Null
    Write-Host "Removed scheduled task: $TaskName" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at $PythonExe. Create/activate .venv first."
}
if (-not (Test-Path $RunnerScript)) {
    Write-Error "Job runner script not found at $RunnerScript"
}

$IntervalMinutes = [Math]::Max(5, $IntervalMinutes)
$quotedPython = '"' + $PythonExe + '"'
$quotedScript = '"' + $RunnerScript + '"'
$taskCommand = "$quotedPython $quotedScript --once --reload-providers"

schtasks /Create /TN $TaskName /SC MINUTE /MO $IntervalMinutes /TR $taskCommand /F | Out-Null

Write-Host "Scheduled task created: $TaskName" -ForegroundColor Green
Write-Host "Interval: every $IntervalMinutes minute(s)" -ForegroundColor Green
Write-Host "Command: $taskCommand" -ForegroundColor DarkGray
