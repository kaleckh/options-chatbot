# Reconfigures "Options AI - Daily Scan" to run as SYSTEM (no password needed).
# Will auto-relaunch as Administrator if needed.

$taskName = "Options AI - Daily Scan"

# Auto-elevate to admin if not already
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Write-Host "Relaunching as Administrator..." -ForegroundColor Yellow
    Start-Process powershell "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host ""
Write-Host "Updating task to run as SYSTEM (no password required)..." -ForegroundColor Cyan

schtasks /change /tn $taskName /ru SYSTEM

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Done! Task will now run at 10:10 AM whether you are logged in or not." -ForegroundColor Green
    Write-Host ""
    schtasks /query /tn $taskName /fo LIST | Select-String "TaskName|Next Run|Status|Logon"
} else {
    Write-Host "Failed to update task." -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
