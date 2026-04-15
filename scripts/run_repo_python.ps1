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

function Get-StableFileStamp([string[]]$Paths, [string]$BaseRoot = "") {
    $parts = New-Object System.Collections.Generic.List[string]
    $normalizedBaseRoot = ""
    if (-not [string]::IsNullOrWhiteSpace($BaseRoot)) {
        $normalizedBaseRoot = [System.IO.Path]::GetFullPath($BaseRoot).TrimEnd('\')
    }
    foreach ($path in $Paths) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path
            $relativePath = [string]$item.Name
            $resolvedPath = [System.IO.Path]::GetFullPath($item.FullName)

            if (-not [string]::IsNullOrWhiteSpace($normalizedBaseRoot)) {
                if ($resolvedPath.StartsWith($normalizedBaseRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                    $candidate = $resolvedPath.Substring($normalizedBaseRoot.Length).TrimStart('\')
                    if (-not [string]::IsNullOrWhiteSpace($candidate)) {
                        $relativePath = $candidate
                    }
                }
            }

            $fileHash = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash.ToLowerInvariant()
            $parts.Add(("{0}|{1}" -f $relativePath, $fileHash))
        }
    }
    return ($parts -join "`n")
}

function Get-RepoTempRoot([string]$RepoRoot) {
    $repoName = Split-Path -Leaf $RepoRoot
    $normalizedRoot = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\').ToLowerInvariant()
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalizedRoot))
    }
    finally {
        $sha256.Dispose()
    }
    $repoHash = ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").Substring(0, 12).ToLowerInvariant()
    $rootName = "$repoName-$repoHash"
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        return Join-Path $env:CODEX_HOME ".tmp\repo-python\$rootName"
    }

    $systemTemp = Get-SystemTempBasePath
    return Join-Path $systemTemp "codex-repo-python\$rootName"
}

function Get-SystemTempBasePath {
    $systemTemp = [System.IO.Path]::GetTempPath().TrimEnd('\')
    if ([string]::IsNullOrWhiteSpace($systemTemp)) {
        throw "A system temp path could not be determined."
    }
    return $systemTemp
}

function Ensure-DirectoryPath([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Test-VenvHasPip([string]$PythonPath) {
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        return $false
    }

    & $PythonPath -m pip --version *> $null
    return ($LASTEXITCODE -eq 0)
}

function Test-VenvHealthy([string]$VenvRoot, [string]$PythonPath) {
    if (-not (Test-Path -LiteralPath $VenvRoot)) {
        return $false
    }

    $configPath = Join-Path $VenvRoot "pyvenv.cfg"
    if (-not (Test-Path -LiteralPath $configPath)) {
        return $false
    }

    return (Test-VenvHasPip -PythonPath $PythonPath)
}

function Remove-VenvDirectory([string]$VenvRoot) {
    if (-not (Test-Path -LiteralPath $VenvRoot)) {
        return
    }

    Remove-Item -LiteralPath $VenvRoot -Recurse -Force -ErrorAction SilentlyContinue
}

function Repair-VenvPip([string]$PythonPath, [string]$VenvRoot) {
    if (-not (Test-Path -LiteralPath $PythonPath)) {
        return $false
    }

    Write-Warning "Attempting to repair pip in repo-local virtualenv at $VenvRoot"
    try {
        & $PythonPath -m ensurepip --upgrade --default-pip
    }
    catch {
        return $false
    }

    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    return (Test-VenvHasPip -PythonPath $PythonPath)
}

function New-RepoVirtualEnv([string[]]$BootstrapCommand, [string]$VenvRoot) {
    if (Test-Path -LiteralPath $VenvRoot) {
        Write-Warning "Detected incomplete repo-local virtualenv at $VenvRoot; recreating it."
        Remove-VenvDirectory -VenvRoot $VenvRoot
    }

    Write-Host "Creating repo-local virtualenv at $VenvRoot"
    if ($BootstrapCommand.Length -gt 1) {
        & $BootstrapCommand[0] $BootstrapCommand[1..($BootstrapCommand.Length - 1)] -m venv $VenvRoot
    }
    else {
        & $BootstrapCommand[0] -m venv $VenvRoot
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Initial virtualenv creation failed; removing partial environment and retrying once."
        Remove-VenvDirectory -VenvRoot $VenvRoot

        if ($BootstrapCommand.Length -gt 1) {
            & $BootstrapCommand[0] $BootstrapCommand[1..($BootstrapCommand.Length - 1)] -m venv $VenvRoot
        }
        else {
            & $BootstrapCommand[0] -m venv $VenvRoot
        }
    }

    if ($LASTEXITCODE -ne 0) {
        $venvPython = Join-Path $VenvRoot "Scripts\python.exe"
        if (-not (Repair-VenvPip -PythonPath $venvPython -VenvRoot $VenvRoot)) {
            throw "Failed to create repo-local virtualenv."
        }
    }
}

function Get-CanonicalRequirements([string]$CanonicalRoot, [string[]]$RepoRequirements, [string]$RepoRoot) {
    $resolvedRepoRoot = [System.IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
    $canonicalRequirements = New-Object System.Collections.Generic.List[string]
    foreach ($path in $RepoRequirements) {
        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }

        $resolvedPath = [System.IO.Path]::GetFullPath($path)
        if ($resolvedPath.StartsWith($resolvedRepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            $relativePath = $resolvedPath.Substring($resolvedRepoRoot.Length).TrimStart('\')
            $canonicalPath = Join-Path $CanonicalRoot $relativePath
            if (Test-Path -LiteralPath $canonicalPath) {
                $canonicalRequirements.Add($canonicalPath)
            }
        }
    }

    return @($canonicalRequirements)
}

function Get-CanonicalVirtualEnvFallback(
    [string]$RepoRoot,
    [string]$CanonicalRoot,
    [string[]]$Requirements,
    [string]$CurrentStamp
) {
    if ($CanonicalRoot -eq $RepoRoot) {
        return $null
    }

    $canonicalRequirements = Get-CanonicalRequirements -CanonicalRoot $CanonicalRoot -RepoRequirements $Requirements -RepoRoot $RepoRoot
    if ($canonicalRequirements.Count -ne $Requirements.Count) {
        return $null
    }

    $canonicalStamp = Get-StableFileStamp -Paths $canonicalRequirements -BaseRoot $CanonicalRoot
    if ($canonicalStamp.TrimEnd("`r", "`n") -ne $CurrentStamp.TrimEnd("`r", "`n")) {
        return $null
    }

    $canonicalVenvRoot = Join-Path $CanonicalRoot ".venv"
    $canonicalVenvPython = Join-Path $canonicalVenvRoot "Scripts\python.exe"
    if (-not (Test-VenvHealthy -VenvRoot $canonicalVenvRoot -PythonPath $canonicalVenvPython)) {
        return $null
    }

    return @{
        VenvRoot = $canonicalVenvRoot
        PythonPath = $canonicalVenvPython
        StampPath = Join-Path $canonicalVenvRoot ".automation-deps-stamp"
        UsingCanonical = $true
    }
}

function Set-RepoTempEnvironment([string]$RepoRoot) {
    $preferredTempRoot = Get-RepoTempRoot -RepoRoot $RepoRoot
    $tempRoot = $preferredTempRoot

    try {
        foreach ($path in @(
            $tempRoot,
            (Join-Path $tempRoot "tmp"),
            (Join-Path $tempRoot "pip-build-tracker")
        )) {
            Ensure-DirectoryPath -Path $path
        }
    }
    catch [System.UnauthorizedAccessException], [System.IO.IOException] {
        $fallbackRoot = Join-Path (Get-SystemTempBasePath) ("codex-repo-python\" + (Split-Path -Leaf $tempRoot))
        Write-Warning "Repo temp root $preferredTempRoot is unavailable ($($_.Exception.Message)); falling back to $fallbackRoot"
        $tempRoot = $fallbackRoot
        foreach ($path in @(
            $tempRoot,
            (Join-Path $tempRoot "tmp"),
            (Join-Path $tempRoot "pip-build-tracker")
        )) {
            Ensure-DirectoryPath -Path $path
        }
    }

    $tmpPath = Join-Path $tempRoot "tmp"
    $pipBuildTracker = Join-Path $tempRoot "pip-build-tracker"

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
    $currentStamp = Get-StableFileStamp -Paths $requirements -BaseRoot $repoRoot
    $activeVenvRoot = $venvRoot
    $activeVenvPython = $venvPython
    $activeStampPath = $stampPath
    $usingCanonicalVenv = $false

    if ((Test-Path -LiteralPath $venvPython) -and -not (Test-VenvHasPip -PythonPath $venvPython)) {
        if (-not (Repair-VenvPip -PythonPath $venvPython -VenvRoot $venvRoot)) {
            Write-Warning "Detected incomplete repo-local virtualenv at $venvRoot; recreating it."
            Remove-VenvDirectory -VenvRoot $venvRoot
        }
    }

    if (-not (Test-VenvHealthy -VenvRoot $venvRoot -PythonPath $venvPython)) {
        $bootstrap = Get-SystemPythonCommand
        try {
            New-RepoVirtualEnv -BootstrapCommand $bootstrap -VenvRoot $venvRoot
        }
        catch {
            $canonicalFallback = Get-CanonicalVirtualEnvFallback -RepoRoot $repoRoot -CanonicalRoot $canonicalRoot -Requirements $requirements -CurrentStamp $currentStamp
            if ($null -eq $canonicalFallback) {
                throw
            }

            $activeVenvRoot = [string]$canonicalFallback.VenvRoot
            $activeVenvPython = [string]$canonicalFallback.PythonPath
            $activeStampPath = [string]$canonicalFallback.StampPath
            $usingCanonicalVenv = $true
            Write-Warning "Repo-local virtualenv bootstrap failed; falling back to the healthy canonical virtualenv at $activeVenvRoot"
        }
    }

    $previousStamp = if (Test-Path -LiteralPath $activeStampPath) { (Get-Content -LiteralPath $activeStampPath -Raw).TrimEnd("`r", "`n") } else { "" }
    $normalizedCurrentStamp = $currentStamp.TrimEnd("`r", "`n")
    if ($ForceInstall -or $previousStamp -ne $normalizedCurrentStamp) {
        $installArgs = @(
            "-m", "pip", "--disable-pip-version-check", "install",
            "-r", (Join-Path $repoRoot "requirements.txt"),
            "-r", (Join-Path $repoRoot "python-backend\requirements.txt")
        )
        if ($usingCanonicalVenv) {
            Write-Warning "Installing worktree dependency updates into the canonical virtualenv at $activeVenvRoot"
        }
        else {
            Write-Host "Installing repo Python dependencies into $activeVenvRoot"
        }
        & $activeVenvPython @installArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install repo Python dependencies."
        }
        Set-Content -LiteralPath $activeStampPath -Value $normalizedCurrentStamp -Encoding UTF8 -NoNewline
    }

    if (-not $CommandArgs -or $CommandArgs.Count -eq 0) {
        Write-Output $activeVenvPython
        exit 0
    }

    $env:PYTHONUTF8 = "1"
    Push-Location $repoRoot
    try {
        & $activeVenvPython @CommandArgs
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
