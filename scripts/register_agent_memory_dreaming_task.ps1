param(
    [string]$TaskName = "OptionsMemoryDreaming",
    [string]$TaskPath = "\",
    [string]$At = "23:45"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $RepoRoot "scripts\run_agent_memory_dreaming.bat"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Missing dreaming runner: $Runner"
}

$triggerTime = [datetime]::ParseExact($At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Runner`"" -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $triggerTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs options-chatbot automated memory dreaming and writes an audit trail. Orchestration memory only; no trading or evidence mutation." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Select-Object TaskName, TaskPath, State
