param(
    [string]$TaskName = "OptionsMemoryMaintenance",
    [string]$TaskPath = "\",
    [string]$At = "06:15",
    [int]$IntervalHours = 6
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $RepoRoot "scripts\run_agent_memory_maintenance.bat"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Missing memory maintenance runner: $Runner"
}

$triggerStart = [datetime]::ParseExact($At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
if ($triggerStart -lt (Get-Date)) {
    $triggerStart = $triggerStart.AddDays(1)
}

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Runner`"" -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $triggerStart `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs options-chatbot memory auto-maintenance. Local orchestration memory only; no trading, broker, scanner, quote import, or evidence mutation." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Select-Object TaskName, TaskPath, State
