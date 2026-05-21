param(
    [switch]$SkipInstall,
    [switch]$Browser
)

$ErrorActionPreference = "Stop"

Push-Location (Join-Path $PSScriptRoot "..")
try {
    if (-not $SkipInstall) {
        python -m pip install -e ".[dev]"
    }

    python -m ruff check src tests scripts
    python -m compileall -q src tests scripts
    python -m pytest -q

    if (Get-Command node -ErrorAction SilentlyContinue) {
        node --check web\shared.js
        node --check web\plan.js
        node --check web\saved.js
        node --check web\account.js
    } else {
        Write-Warning "Node.js not found; skipped frontend JavaScript syntax checks."
    }

    if ($Browser) {
        python scripts/playwright_integration.py
    } else {
        Write-Host "Optional browser integration: start local servers, run 'python -m playwright install chromium' once, then run 'powershell -File scripts/verify.ps1 -SkipInstall -Browser'." -ForegroundColor Cyan
    }
} finally {
    Pop-Location
}
