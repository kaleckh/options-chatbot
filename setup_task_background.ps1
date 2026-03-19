# Reconfigures "Options AI - Daily Scan" to run without requiring login.
# Run this once from PowerShell (right-click PowerShell > Run as Administrator
# is NOT required — your own credentials are sufficient).

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

# Update the task: run as user regardless of login state, wake to run
$result = schtasks /change `
    /tn $taskName `
    /ru $username `
    /rp $password `
    /it

if ($LASTEXITCODE -eq 0) {
    # Also enable wake-from-sleep via XML patch
    $xml = (schtasks /query /tn $taskName /xml) -join "`n"
    if ($xml -notmatch "<WakeToRun>true</WakeToRun>") {
        $xml = $xml -replace "<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>", "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        $xml = $xml -replace "<StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>",       "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
        $xml = $xml -replace "</Settings>", "  <WakeToRun>true</WakeToRun>`n  </Settings>"
        $tmpXml = "$env:TEMP\options_scan_task.xml"
        $xml | Out-File -FilePath $tmpXml -Encoding UTF8
        schtasks /delete /tn $taskName /f | Out-Null
        schtasks /create /tn $taskName /xml $tmpXml /ru $username /rp $password /f
        Remove-Item $tmpXml -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Host "Done! Task updated:" -ForegroundColor Green
    schtasks /query /tn $taskName /fo LIST | Select-String "TaskName|Next Run|Status|Logon"
} else {
    Write-Host "Failed to update task. Check your password and try again." -ForegroundColor Red
}

Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
