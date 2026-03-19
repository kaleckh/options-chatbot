# Reconfigures "Options AI - Daily Scan" to run without requiring login.
# Run this once from PowerShell.

$taskName = "Options AI - Daily Scan"
$username = "DESKTOP-LS7OBTA\cardi"

Write-Host ""
Write-Host "This will update the scheduled task to run whether or not you are logged in."
Write-Host "Your password is passed directly to Windows Task Scheduler and is not stored"
Write-Host "or transmitted anywhere else."
Write-Host ""

$cred = Get-Credential -UserName $username -Message "Enter your Windows login password for user 'cardi'"

if (-not $cred) {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit
}

$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password)
)

schtasks /change /tn $taskName /ru $username /rp $password

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Done! Task updated:" -ForegroundColor Green
    schtasks /query /tn $taskName /fo LIST | Select-String "TaskName|Next Run|Status|Logon"
} else {
    Write-Host "Failed to update task. Check your password and try again." -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
