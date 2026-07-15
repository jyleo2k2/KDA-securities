[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$StateRoot = Join-Path $env:LOCALAPPDATA "PensionCopilot"
$PidFile = Join-Path $StateRoot "server-processes.json"

function Show-Message {
    param([string]$Message)

    if (-not $Quiet) {
        $shell = New-Object -ComObject WScript.Shell
        [void]$shell.Popup($Message, 0, "Pension Copilot", 0x40)
    }
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId"
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-RecordedProcess {
    param([object]$Record)

    if ($null -eq $Record -or $null -eq $Record.pid -or $null -eq $Record.started_at) {
        return
    }

    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return
    }

    $recordedStart = [DateTime]::Parse([string]$Record.started_at).ToUniversalTime()
    $actualStart = $process.StartTime.ToUniversalTime()
    if ([Math]::Abs(($actualStart - $recordedStart).TotalSeconds) -gt 2) {
        return
    }

    Stop-ProcessTree -ProcessId $process.Id
}

try {
    if (-not (Test-Path -LiteralPath $PidFile)) {
        Show-Message -Message "No server started by this launcher was found."
        exit 0
    }

    $records = Get-Content -LiteralPath $PidFile -Raw | ConvertFrom-Json
    $backendProperty = $records.PSObject.Properties["backend"]
    if ($null -ne $backendProperty) {
        Stop-RecordedProcess -Record $backendProperty.Value
    }
    $frontendProperty = $records.PSObject.Properties["frontend"]
    if ($null -ne $frontendProperty) {
        Stop-RecordedProcess -Record $frontendProperty.Value
    }

    Remove-Item -LiteralPath $PidFile -Force
    Show-Message -Message "Pension Copilot servers were stopped."
}
catch {
    if (-not $Quiet) {
        $shell = New-Object -ComObject WScript.Shell
        [void]$shell.Popup($_.Exception.Message, 0, "Pension Copilot shutdown failed", 0x10)
    }
    exit 1
}
