param(
    [switch]$SkipInstall,
    [switch]$Browser
)

$ErrorActionPreference = "Stop"

function Assert-NativeCommandSucceeded {
    param([Parameter(Mandatory = $true)][string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

Push-Location (Join-Path $PSScriptRoot "..")
try {
    if (-not $SkipInstall) {
        python -m pip install -e ".[dev]"
        Assert-NativeCommandSucceeded "Dependency installation"
    }

    python -m ruff check src tests scripts
    Assert-NativeCommandSucceeded "Ruff"
    python -m compileall -q src tests scripts
    Assert-NativeCommandSucceeded "Python compilation"
    python -m pytest -q
    Assert-NativeCommandSucceeded "Pytest"

    if (Get-Command node -ErrorAction SilentlyContinue) {
        node --check web\shared.js
        Assert-NativeCommandSucceeded "shared.js syntax check"
        node --check web\plan.js
        Assert-NativeCommandSucceeded "plan.js syntax check"
        node --check web\saved.js
        Assert-NativeCommandSucceeded "saved.js syntax check"
        node --check web\account.js
        Assert-NativeCommandSucceeded "account.js syntax check"
    } else {
        Write-Warning "Node.js not found; skipped frontend JavaScript syntax checks."
    }

    if ($Browser) {
        python scripts/playwright_integration.py
        Assert-NativeCommandSucceeded "Playwright integration"
    } else {
        Write-Host "Optional browser integration: start local servers, run 'python -m playwright install chromium' once, then run 'powershell -File scripts/verify.ps1 -SkipInstall -Browser'." -ForegroundColor Cyan
    }
} finally {
    Pop-Location
}
