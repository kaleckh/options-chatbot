param(
    [switch]$ForceInstall,
    [switch]$SkipArtifactSync,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SystemPythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3.12")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3.12 bootstrap executable was not found."
}

function Get-StableFileStamp([string[]]$Paths) {
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($path in $Paths) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path
            $parts.Add(("{0}|{1}|{2}" -f $item.FullName, $item.Length, $item.LastWriteTimeUtc.Ticks))
        }
    }
    return ($parts -join "`n")
}

function Get-RepoTempRoot([string]$RepoRoot) {
    $repoName = Split-Path -Leaf $RepoRoot
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        return Join-Path $env:CODEX_HOME ".tmp\repo-python\$repoName"
    }

    $systemTemp = [System.IO.Path]::GetTempPath().TrimEnd('\')
    return Join-Path $systemTemp "codex-repo-python\$repoName"
}

function Set-RepoTempEnvironment([string]$RepoRoot) {
    $tempRoot = Get-RepoTempRoot -RepoRoot $RepoRoot
    $tmpPath = Join-Path $tempRoot "tmp"
    $pipBuildTracker = Join-Path $tempRoot "pip-build-tracker"

    foreach ($path in @($tempRoot, $tmpPath, $pipBuildTracker)) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }

    $names = @("TMP", "TEMP", "TMPDIR", "PIP_BUILD_TRACKER")
    $backup = @{}
    foreach ($name in $names) {
        $backup[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    [Environment]::SetEnvironmentVariable("TMP", $tmpPath, "Process")
    [Environment]::SetEnvironmentVariable("TEMP", $tmpPath, "Process")
    [Environment]::SetEnvironmentVariable("TMPDIR", $tmpPath, "Process")
    [Environment]::SetEnvironmentVariable("PIP_BUILD_TRACKER", $pipBuildTracker, "Process")

    return @{
        Names = $names
        Backup = $backup
    }
}

function Restore-RepoTempEnvironment($Snapshot) {
    if (-not $Snapshot) {
        return
    }

    foreach ($name in @($Snapshot.Names)) {
        $previous = $null
        if ($Snapshot.Backup.ContainsKey($name)) {
            $previous = $Snapshot.Backup[$name]
        }
        [Environment]::SetEnvironmentVariable($name, $previous, "Process")
    }
}

function Get-ProcessEnvironmentVariableNames([string]$Prefix) {
    $names = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
    $environment = [System.Environment]::GetEnvironmentVariables("Process")
    foreach ($name in $environment.Keys) {
        $stringName = [string]$name
        if ([string]::IsNullOrEmpty($Prefix) -or $stringName.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            $null = $names.Add($stringName)
        }
    }
    return @($names)
}

function Enable-ProcessGitSafeDirectory([string]$SafeDirectory) {
    $trackedNames = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
    $backup = @{}

    foreach ($name in (Get-ProcessEnvironmentVariableNames -Prefix "GIT_CONFIG_")) {
        $trackedNames.Add($name) | Out-Null
        $backup[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    }

    $trackedNames.Add("GIT_CONFIG_COUNT") | Out-Null
    if (-not $backup.ContainsKey("GIT_CONFIG_COUNT")) {
        $backup["GIT_CONFIG_COUNT"] = [Environment]::GetEnvironmentVariable("GIT_CONFIG_COUNT", "Process")
    }

    $existingCount = 0
    $rawCount = [Environment]::GetEnvironmentVariable("GIT_CONFIG_COUNT", "Process")
    if (-not [string]::IsNullOrWhiteSpace($rawCount)) {
        try {
            $existingCount = [int]$rawCount
        }
        catch {
            $existingCount = 0
        }
    }

    $newIndex = $existingCount
    $keyName = "GIT_CONFIG_KEY_$newIndex"
    $valueName = "GIT_CONFIG_VALUE_$newIndex"
    foreach ($name in @($keyName, $valueName)) {
        $trackedNames.Add($name) | Out-Null
        if (-not $backup.ContainsKey($name)) {
            $backup[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        }
    }

    [Environment]::SetEnvironmentVariable("GIT_CONFIG_COUNT", [string]($existingCount + 1), "Process")
    [Environment]::SetEnvironmentVariable($keyName, "safe.directory", "Process")
    [Environment]::SetEnvironmentVariable($valueName, $SafeDirectory, "Process")

    return @{
        TrackedNames = @($trackedNames)
        Backup = $backup
    }
}

function Restore-ProcessGitEnvironment($Snapshot) {
    if (-not $Snapshot) {
        return
    }

    foreach ($name in @($Snapshot.TrackedNames)) {
        $previous = $null
        if ($Snapshot.Backup.ContainsKey($name)) {
            $previous = $Snapshot.Backup[$name]
        }
        [Environment]::SetEnvironmentVariable($name, $previous, "Process")
    }
}

function Get-CanonicalRepoRoot([string]$RepoRoot) {
    $worktreeOutput = & git -C $RepoRoot worktree list --porcelain 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $worktreeOutput) {
        return $RepoRoot
    }

    foreach ($line in $worktreeOutput) {
        if ($line.StartsWith("worktree ")) {
            $candidate = $line.Substring(9).Trim()
            if ($candidate) {
                return [System.IO.Path]::GetFullPath($candidate)
            }
        }
    }

    return $RepoRoot
}

function Sync-ValidationArtifacts([string]$CanonicalRoot, [string]$RepoRoot) {
    if ($CanonicalRoot -eq $RepoRoot) {
        return
    }

    $sourceValidationRoot = Join-Path $CanonicalRoot "data\options-validation"
    $targetValidationRoot = Join-Path $RepoRoot "data\options-validation"
    $targetLatestDaily = Join-Path $targetValidationRoot "runs\latest_daily.json"

    if (-not (Test-Path -LiteralPath $sourceValidationRoot)) {
        return
    }

    if (Test-Path -LiteralPath $targetLatestDaily) {
        return
    }

    $targetParent = Split-Path -Parent $targetValidationRoot
    if (-not (Test-Path -LiteralPath $targetParent)) {
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    }

    Write-Host "Syncing validation artifacts from $CanonicalRoot"
    try {
        if (Test-Path -LiteralPath $targetValidationRoot) {
            Copy-Item -LiteralPath (Join-Path $sourceValidationRoot "*") -Destination $targetValidationRoot -Recurse -Force
        }
        else {
            Copy-Item -LiteralPath $sourceValidationRoot -Destination $targetValidationRoot -Recurse -Force
        }
    }
    catch {
        Write-Warning "Validation artifact sync failed and will be skipped: $($_.Exception.Message)"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir ".."))
$gitEnvSnapshot = Enable-ProcessGitSafeDirectory -SafeDirectory $repoRoot
$tempEnvSnapshot = Set-RepoTempEnvironment -RepoRoot $repoRoot
try {
    $canonicalRoot = Get-CanonicalRepoRoot -RepoRoot $repoRoot

    if (-not $SkipArtifactSync) {
        Sync-ValidationArtifacts -CanonicalRoot $canonicalRoot -RepoRoot $repoRoot
    }

    $venvRoot = Join-Path $repoRoot ".venv"
    $venvPython = Join-Path $venvRoot "Scripts\python.exe"
    $stampPath = Join-Path $venvRoot ".automation-deps-stamp"
    $requirements = @(
        (Join-Path $repoRoot "requirements.txt"),
        (Join-Path $repoRoot "pyproject.toml"),
        (Join-Path $repoRoot "python-backend\requirements.txt")
    ) | Where-Object { Test-Path -LiteralPath $_ }
    $currentStamp = Get-StableFileStamp -Paths $requirements

    if (-not (Test-Path -LiteralPath $venvPython)) {
        $bootstrap = Get-SystemPythonCommand
        Write-Host "Creating repo-local virtualenv at $venvRoot"
        if ($bootstrap.Length -gt 1) {
            & $bootstrap[0] $bootstrap[1..($bootstrap.Length - 1)] -m venv $venvRoot
        }
        else {
            & $bootstrap[0] -m venv $venvRoot
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create repo-local virtualenv."
        }
    }

    $previousStamp = if (Test-Path -LiteralPath $stampPath) { (Get-Content -LiteralPath $stampPath -Raw).TrimEnd("`r", "`n") } else { "" }
    $normalizedCurrentStamp = $currentStamp.TrimEnd("`r", "`n")
    if ($ForceInstall -or $previousStamp -ne $normalizedCurrentStamp) {
        $installArgs = @(
            "-m", "pip", "--disable-pip-version-check", "install",
            "-r", (Join-Path $repoRoot "requirements.txt"),
            "-r", (Join-Path $repoRoot "python-backend\requirements.txt")
        )
        Write-Host "Installing repo Python dependencies into $venvRoot"
        & $venvPython @installArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install repo Python dependencies."
        }
        Set-Content -LiteralPath $stampPath -Value $normalizedCurrentStamp -Encoding UTF8 -NoNewline
    }

    if (-not $CommandArgs -or $CommandArgs.Count -eq 0) {
        Write-Output $venvPython
        exit 0
    }

    $env:PYTHONUTF8 = "1"
    Push-Location $repoRoot
    try {
        & $venvPython @CommandArgs
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
finally {
    Restore-RepoTempEnvironment -Snapshot $tempEnvSnapshot
    Restore-ProcessGitEnvironment -Snapshot $gitEnvSnapshot
}
