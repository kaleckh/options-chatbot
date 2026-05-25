# Run this as Administrator to register the daily scan task.
# Right-click -> Run as Administrator

$taskName = "Options AI - Daily Scan"
$pythonPath = "C:\Python312\python.exe"
$scriptPath = "C:\Users\kalec\options-chatbot\auto_scan.py"
$batchPath = "C:\Users\kalec\options-chatbot\run_scan.bat"
$workDir = "C:\Users\kalec\options-chatbot"

# Auto-elevate
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Write-Host "Relaunching as Administrator..." -ForegroundColor Yellow
    Start-Process powershell "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "Creating scheduled task: $taskName" -ForegroundColor Cyan
Write-Host "  Python: $pythonPath"
Write-Host "  Script: $scriptPath"
Write-Host "  Wrapper: $batchPath"
Write-Host "  Playbook: bullish_pullback_observation"
Write-Host "  Time: 10:10 AM daily (Mon-Fri)"
Write-Host ""

# Create the task
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batchPath`"" -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Daily -At "10:10AM"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force

Write-Host ""
Write-Host "Task registered!" -ForegroundColor Green
Get-ScheduledTask -TaskName $taskName | Format-List TaskName, State

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
