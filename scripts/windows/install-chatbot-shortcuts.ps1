[CmdletBinding()]
param(
    [string]$RepoRoot,
    [switch]$Quiet,
    [switch]$IncludeDevelopmentShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$StartScript = Join-Path $RepoRoot "scripts\windows\start-chatbot.ps1"
$StopScript = Join-Path $RepoRoot "scripts\windows\stop-chatbot.ps1"
$Desktop = [Environment]::GetFolderPath("Desktop")
$PowerShell = Join-Path $PSHOME "powershell.exe"

if (-not (Test-Path -LiteralPath $StartScript)) {
    throw "Start script not found: $StartScript"
}
if (-not (Test-Path -LiteralPath $StopScript)) {
    throw "Stop script not found: $StopScript"
}
if (-not (Test-Path -LiteralPath $Desktop)) {
    throw "Windows Desktop path not found."
}

$shell = New-Object -ComObject WScript.Shell

function New-ChatbotShortcut {
    param(
        [string]$Name,
        [string]$ScriptPath,
        [string]$Description,
        [string]$IconLocation,
        [string]$AdditionalArguments = ""
    )

    $shortcutPath = Join-Path $Desktop "$Name.lnk"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $PowerShell
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"$AdditionalArguments"
    $shortcut.WorkingDirectory = $RepoRoot
    $shortcut.Description = $Description
    $shortcut.IconLocation = $IconLocation
    $shortcut.Save()
}

$shellIcon = Join-Path $env:SystemRoot "System32\SHELL32.dll"
New-ChatbotShortcut `
    -Name "Pension Copilot Chatbot" `
    -ScriptPath $StartScript `
    -Description "Start the Pension Copilot chatbot from the main branch." `
    -IconLocation "$shellIcon,220"
New-ChatbotShortcut `
    -Name "Pension Copilot Stop" `
    -ScriptPath $StopScript `
    -Description "Stop the Pension Copilot servers started by the launcher." `
    -IconLocation "$shellIcon,131"

if ($IncludeDevelopmentShortcut) {
    New-ChatbotShortcut `
        -Name "Pension Copilot Chatbot DEV" `
        -ScriptPath $StartScript `
        -Description "Test the Pension Copilot chatbot from a non-main development branch." `
        -IconLocation "$shellIcon,220" `
        -AdditionalArguments " -AllowNonMain"
}

if (-not $Quiet) {
    [void]$shell.Popup(
        "Pension Copilot shortcuts were created on the Desktop.",
        0,
        "Pension Copilot",
        0x40
    )
}
