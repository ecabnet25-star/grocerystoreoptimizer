$ErrorActionPreference = "Stop"

Write-Host "Running beta smoke checks..."

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = "src"
$python = "c:/Users/Ethan/Downloads/New folder/.venv/Scripts/python.exe"

& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed"
}

$health = & $python -c "from grocery_optimizer.api.app import health; print(health()['status'])"
$ready = & $python -c "from grocery_optimizer.api.app import ready; print(ready()['ready'])"

Write-Host "Health: $health"
Write-Host "Ready:  $ready"

if ($health -ne "ok" -or $ready -ne "True") {
    throw "Health/readiness checks failed"
}

Write-Host "Beta smoke checks passed."
