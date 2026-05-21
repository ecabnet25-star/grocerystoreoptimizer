# Grocery Optimizer Launch Script
# One-button launcher for Docker or local Python mode

param(
    [ValidateSet("Auto", "Docker", "Local")]
    [string]$Mode = "Auto",
    [switch]$NoBrowser = $false,
    [switch]$Build = $false,
    [switch]$Stop = $false
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function ConvertTo-PSQuotedString {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function New-CommandInvocation {
    param(
        [string]$Executable,
        [string[]]$Arguments
    )

    $tokens = @("& " + (ConvertTo-PSQuotedString -Value $Executable))
    foreach ($arg in $Arguments) {
        $tokens += (ConvertTo-PSQuotedString -Value $arg)
    }

    return ($tokens -join " ")
}

function Get-PythonInvocation {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{ Executable = $venvPython; PrefixArgs = @() }
    }
    if (Test-CommandAvailable -Name "python") {
        return @{ Executable = "python"; PrefixArgs = @() }
    }
    if (Test-CommandAvailable -Name "py") {
        return @{ Executable = "py"; PrefixArgs = @("-3") }
    }
    return $null
}

function Show-LivePricingProviderStatus {
    $providerConfigPath = Join-Path $ProjectRoot "config\live_pricing\providers.json"
    if (-not (Test-Path $providerConfigPath)) {
        Write-Host "[WARN] Live pricing config not found at $providerConfigPath" -ForegroundColor Yellow
        return
    }

    try {
        $configRaw = Get-Content -Path $providerConfigPath -Raw
        $config = $configRaw | ConvertFrom-Json
    } catch {
        Write-Host "[WARN] Could not parse live pricing config JSON." -ForegroundColor Yellow
        return
    }

    $providers = @($config.providers)
    if ($providers.Count -eq 0) {
        Write-Host "[WARN] No live pricing providers configured." -ForegroundColor Yellow
        return
    }

    $enabled = @($providers | Where-Object { $_.enabled -eq $true })
    if ($enabled.Count -eq 0) {
        Write-Host "[WARN] Live pricing providers are configured but all disabled." -ForegroundColor Yellow
        Write-Host "  Enable at least one provider in config/live_pricing/providers.json" -ForegroundColor DarkYellow
        return
    }

    Write-Host "[OK] Live pricing providers enabled: $($enabled.Count)" -ForegroundColor Green
    foreach ($provider in $enabled) {
        $providerId = [string]$provider.id
        $apiKeyEnv = [string]$provider.api_key_env
        if ($apiKeyEnv) {
            $apiValue = [Environment]::GetEnvironmentVariable($apiKeyEnv)
            if ([string]::IsNullOrWhiteSpace($apiValue)) {
                Write-Host "  [WARN] $providerId missing env var: $apiKeyEnv" -ForegroundColor Yellow
            } else {
                Write-Host "  [OK] $providerId API key env present: $apiKeyEnv" -ForegroundColor Green
            }
        } else {
            Write-Host "  [OK] $providerId enabled (no API key env required)" -ForegroundColor Green
        }
    }
}

function Show-AssistantProviderStatus {
    $assistantMode = [Environment]::GetEnvironmentVariable("GROCERY_ASSISTANT_MODE", "Process")
    if ([string]::IsNullOrWhiteSpace($assistantMode)) {
        $assistantMode = [Environment]::GetEnvironmentVariable("GROCERY_ASSISTANT_MODE", "User")
    }
    if ([string]::IsNullOrWhiteSpace($assistantMode)) {
        $assistantMode = "hybrid"
    }
    $assistantMode = $assistantMode.ToLowerInvariant()

    $ollamaModel = [Environment]::GetEnvironmentVariable("GROCERY_ASSISTANT_OLLAMA_MODEL", "Process")
    if ([string]::IsNullOrWhiteSpace($ollamaModel)) {
        $ollamaModel = [Environment]::GetEnvironmentVariable("GROCERY_ASSISTANT_OLLAMA_MODEL", "User")
    }
    if ([string]::IsNullOrWhiteSpace($ollamaModel)) {
        $ollamaModel = "llama3.2:3b"
    }

    Write-Host "[INFO] Assistant mode: $assistantMode" -ForegroundColor Cyan
    if ($assistantMode -in @("hybrid", "ollama")) {
        $ollamaRunning = Test-NetConnection -ComputerName "127.0.0.1" -Port 11434 -WarningAction SilentlyContinue
        if ($ollamaRunning.TcpTestSucceeded) {
            Write-Host "  [OK] Ollama reachable on 127.0.0.1:11434 (model: $ollamaModel)" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Ollama not reachable on 127.0.0.1:11434. Assistant will use fallback mode." -ForegroundColor Yellow
            Write-Host "  Install/start Ollama and run: ollama pull $ollamaModel" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  [OK] Rule-based assistant enabled (no model server required)." -ForegroundColor Green
    }
}

function Import-LivePricingEnv {
    $flippKey = [Environment]::GetEnvironmentVariable("LIVE_PRICING_FLIPP_KEY", "User")
    if (-not [string]::IsNullOrWhiteSpace($flippKey)) {
        $env:LIVE_PRICING_FLIPP_KEY = $flippKey
    }
}

function Start-LocalStack {
    $pythonInvoke = Get-PythonInvocation
    if (-not $pythonInvoke) {
        Write-Host "[ERROR] Python was not found (.venv, python, or py launcher)." -ForegroundColor Red
        Write-Host "  Install Python or create .venv before using local mode." -ForegroundColor Yellow
        exit 1
    }

    Write-Host "[OK] Using Python executable: $($pythonInvoke.Executable)" -ForegroundColor Green
    Import-LivePricingEnv
    Show-LivePricingProviderStatus
    Show-AssistantProviderStatus
    Write-Host "`nStarting local API and web servers..." -ForegroundColor Yellow

    $apiArgs = @($pythonInvoke.PrefixArgs + @(
        "-m",
        "uvicorn",
        "grocery_optimizer.api.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--app-dir",
        "src"
    ))
    $webArgs = @($pythonInvoke.PrefixArgs + @(
        "-m",
        "http.server",
        "8080",
        "--directory",
        "web"
    ))

    $projectRootLiteral = ConvertTo-PSQuotedString -Value $ProjectRoot
    $apiInvoke = New-CommandInvocation -Executable $pythonInvoke.Executable -Arguments $apiArgs
    $webInvoke = New-CommandInvocation -Executable $pythonInvoke.Executable -Arguments $webArgs

    $apiCmd = "Set-Location $projectRootLiteral; `$env:PYTHONPATH='src'; $apiInvoke"
    $webCmd = "Set-Location $projectRootLiteral; $webInvoke"

    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $apiCmd | Out-Null
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $webCmd | Out-Null

    Start-Sleep -Seconds 2

    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:8080" | Out-Null
    }

    Write-Host "`n[OK] Local stack launch triggered." -ForegroundColor Green
    Write-Host "Application Status:" -ForegroundColor Cyan
    Write-Host "  Open this first: http://127.0.0.1:8080" -ForegroundColor Cyan
    Write-Host "  Web UI:  http://127.0.0.1:8080" -ForegroundColor Green
    Write-Host "  API:     http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "  Docs:    http://127.0.0.1:8000/docs" -ForegroundColor Green
    if ($NoBrowser) {
        Write-Host "  Browser auto-open was disabled by -NoBrowser." -ForegroundColor DarkGray
    }
    Write-Host "`nTip: Close the two PowerShell windows to stop local servers." -ForegroundColor Yellow
}

function Start-DockerStack {
    Write-Host "`nStarting Docker application stack..." -ForegroundColor Yellow
    if ($Build) {
        docker compose up -d --build
    } else {
        docker compose up -d
    }

    if (-not $NoBrowser) {
        Start-Sleep -Seconds 2
        Start-Process "http://localhost:8080" | Out-Null
    }

    Write-Host "`n[OK] Docker stack started in detached mode." -ForegroundColor Green
    Write-Host "Application Status:" -ForegroundColor Cyan
    Write-Host "  Open this first: http://localhost:8080" -ForegroundColor Cyan
    Write-Host "  Web UI:  http://localhost:8080" -ForegroundColor Green
    Write-Host "  API:     http://localhost:8000" -ForegroundColor Green
    Write-Host "  Docs:    http://localhost:8000/docs" -ForegroundColor Green
    if ($NoBrowser) {
        Write-Host "  Browser auto-open was disabled by -NoBrowser." -ForegroundColor DarkGray
    }
    Write-Host "`nTip: Run 'docker compose down' to stop the stack." -ForegroundColor Yellow
}

function Stop-LocalStack {
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
        return
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
    } else {
        Write-Host "[WARN] No processes were stopped." -ForegroundColor Yellow
    }
}

Write-Host "Grocery Optimizer Launch" -ForegroundColor Cyan
Write-Host "========================" -ForegroundColor Cyan
Write-Host "Mode requested: $Mode" -ForegroundColor DarkGray

if ($Stop) {
    Stop-LocalStack
    exit 0
}

$dockerInstalled = Test-CommandAvailable -Name "docker"
$dockerRunning = $false
if ($dockerInstalled) {
    try { docker ps 2>&1 | Out-Null } catch {}
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
    }
}

switch ($Mode) {
    "Docker" {
        if (-not $dockerInstalled) {
            Write-Host "[ERROR] Docker command not found in PATH." -ForegroundColor Red
            exit 1
        }
        if (-not $dockerRunning) {
            Write-Host "[ERROR] Docker is installed but daemon is not running." -ForegroundColor Red
            Write-Host "  Start Docker Desktop and retry, or use -Mode Local." -ForegroundColor Yellow
            exit 1
        }
        Start-DockerStack
    }
    "Local" {
        Start-LocalStack
    }
    default {
        if ($dockerInstalled -and $dockerRunning) {
            Write-Host "[OK] Docker detected. Using Docker mode." -ForegroundColor Green
            Start-DockerStack
        } else {
            Write-Host "[WARN] Docker unavailable. Falling back to Local mode." -ForegroundColor Yellow
            Start-LocalStack
        }
    }
}
