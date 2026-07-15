[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [switch]$AllowNonMain
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BackendUrl = "http://127.0.0.1:8000"
$FrontendUrl = "http://127.0.0.1:5173"
$ChatUrl = "$FrontendUrl/#guide"
$StateRoot = Join-Path $env:LOCALAPPDATA "PensionCopilot"
$LogRoot = Join-Path $StateRoot "logs"
$PidFile = Join-Path $StateRoot "server-processes.json"
$BackendLog = Join-Path $LogRoot "backend.log"
$BackendErrorLog = Join-Path $LogRoot "backend-error.log"
$FrontendLog = Join-Path $LogRoot "frontend.log"
$FrontendErrorLog = Join-Path $LogRoot "frontend-error.log"
$CreatedPidFile = $false

function Show-Message {
    param(
        [string]$Message,
        [string]$Title = "Pension Copilot"
    )

    $shell = New-Object -ComObject WScript.Shell
    [void]$shell.Popup($Message, 0, $Title, 0x30)
}

function Test-HttpEndpoint {
    param([string]$Uri)

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Test-LocalPort {
    param([int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(300) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function New-ProcessRecord {
    param([System.Diagnostics.Process]$Process)

    return [ordered]@{
        pid = $Process.Id
        started_at = $Process.StartTime.ToUniversalTime().ToString("o")
    }
}

function Wait-ForEndpoint {
    param(
        [string]$Uri,
        [int]$TimeoutSeconds = 45
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-HttpEndpoint -Uri $Uri) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

try {
    $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
    $FrontendRoot = Join-Path $RepoRoot "frontend"
    $EnvFile = Join-Path $RepoRoot ".env"

    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
        throw "Repository path not found: $RepoRoot"
    }

    $branch = (& git -C $RepoRoot branch --show-current 2>$null).Trim()
    if (-not $AllowNonMain -and $branch -ne "main") {
        throw "Current branch is not main: $branch`nThe launcher will not switch branches automatically."
    }

    if (-not (Test-Path -LiteralPath $EnvFile)) {
        throw ".env is missing. Check the project root configuration."
    }
    $envText = Get-Content -LiteralPath $EnvFile -Raw
    if ($envText -notmatch "(?m)^\s*DATABASE_URL\s*=\s*\S+") {
        throw "DATABASE_URL is not configured in .env."
    }

    $uvCommand = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if ($null -eq $uvCommand) {
        $uvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
    }
    if ($null -eq $uvCommand) {
        throw "uv was not found. Check the uv installation and PATH."
    }

    $npmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        throw "npm was not found. Check the Node.js installation and PATH."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
        throw "Frontend dependencies are missing. Run npm install once in frontend."
    }

    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

    $backendReady = Test-HttpEndpoint -Uri "$BackendUrl/health"
    $frontendReady = Test-HttpEndpoint -Uri $FrontendUrl
    if ($backendReady -and $frontendReady) {
        Start-Process $ChatUrl
        exit 0
    }

    if (-not $backendReady -and (Test-LocalPort -Port 8000)) {
        throw "Port 8000 is occupied by another program."
    }
    if (-not $frontendReady -and (Test-LocalPort -Port 5173)) {
        throw "Port 5173 is occupied by another program."
    }

    $records = [ordered]@{}

    if (-not $backendReady) {
        $backend = Start-Process `
            -FilePath $uvCommand.Source `
            -ArgumentList @(
                "run", "uvicorn", "backend.app.main:app",
                "--host", "127.0.0.1", "--port", "8000"
            ) `
            -WorkingDirectory $RepoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $BackendLog `
            -RedirectStandardError $BackendErrorLog `
            -PassThru
        $records.backend = New-ProcessRecord -Process $backend
        $records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $PidFile -Encoding UTF8
        $CreatedPidFile = $true
    }

    if (-not $frontendReady) {
        $frontend = Start-Process `
            -FilePath $npmCommand.Source `
            -ArgumentList @(
                "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"
            ) `
            -WorkingDirectory $FrontendRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $FrontendLog `
            -RedirectStandardError $FrontendErrorLog `
            -PassThru
        $records.frontend = New-ProcessRecord -Process $frontend
        $records | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $PidFile -Encoding UTF8
        $CreatedPidFile = $true
    }

    if (-not (Wait-ForEndpoint -Uri "$BackendUrl/health")) {
        throw "The backend did not start before the timeout.`n$BackendErrorLog"
    }
    if (-not (Wait-ForEndpoint -Uri $FrontendUrl)) {
        throw "The frontend did not start before the timeout.`n$FrontendErrorLog"
    }

    Start-Process $ChatUrl
}
catch {
    if ($CreatedPidFile -and (Test-Path -LiteralPath $PidFile)) {
        # The stop script validates each recorded PID and start time before cleanup.
        & (Join-Path $PSScriptRoot "stop-chatbot.ps1") -RepoRoot $RepoRoot -Quiet
    }
    Show-Message -Message $_.Exception.Message -Title "Pension Copilot startup failed"
    exit 1
}
