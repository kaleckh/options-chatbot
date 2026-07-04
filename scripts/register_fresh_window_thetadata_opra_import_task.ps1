param(
    [string]$TaskName = "OptionsFreshWindowThetaDataOPRAImport",
    [string]$TaskPath = "\",
    [string]$At = "17:30"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $RepoRoot "scripts\run_fresh_window_thetadata_opra_import.bat"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Missing fresh-window ThetaData OPRA runner: $Runner"
}

$triggerTime = [datetime]::ParseExact($At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Runner`"" -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $triggerTime
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs the tokened options-chatbot fresh-window ThetaData OPRA/NBBO quote import after market close, then refreshes materializer/parity readbacks. No scanner, auto-track, append, broker, proof-bar, or promotion changes." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName -TaskPath $TaskPath | Select-Object TaskName, TaskPath, State
