$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoUrl = "https://github.com/Lin-Yu-kuan/yt-sum.git"
$ZipUrl = "https://github.com/Lin-Yu-kuan/yt-sum/archive/refs/heads/main.zip"
$InstallDir = if ($env:YTSUM_DIR) { $env:YTSUM_DIR } else { Join-Path $env:USERPROFILE "YT-Sum" }

function Test-IsInteractive {
    try {
        return [Environment]::UserInteractive -and (-not [Console]::IsInputRedirected)
    } catch {
        return $false
    }
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$DefaultYes = $true
    )
    if (-not (Test-IsInteractive)) {
        return $DefaultYes
    }
    try {
        $ans = Read-Host $Prompt
    } catch {
        return $DefaultYes
    }
    if ([string]::IsNullOrWhiteSpace($ans)) {
        return $DefaultYes
    }
    return ($ans.Trim() -match "^(y|yes)$")
}

function Resolve-OptionalBool {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    $norm = $Value.Trim().ToLowerInvariant()
    if ($norm -in @("1", "true", "y", "yes")) { return $true }
    if ($norm -in @("0", "false", "n", "no")) { return $false }
    return $null
}

function Invoke-NativeQuiet {
    param(
        [string]$Exe,
        [string[]]$ArgList
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Exe @ArgList 2>$null
        $code = $LASTEXITCODE
        return @{
            ExitCode = $code
            Output = ($output | Out-String).Trim()
        }
    } catch {
        return @{
            ExitCode = 1
            Output = ""
        }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Invoke-NativeChecked {
    param(
        [string]$Exe,
        [string[]]$ArgList,
        [string]$ErrorMessage
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @ArgList
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    if ($code -ne 0) {
        throw $ErrorMessage
    }
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @()
    if ($machinePath) { $parts += $machinePath }
    if ($userPath) { $parts += $userPath }
    if ($parts.Count -gt 0) {
        $env:Path = ($parts -join ";")
    }
}

function Find-Python310 {
    $candidates = @()

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $candidates += @{ Exe = $pyCmd.Source; Args = @("-3") }
    }

    foreach ($name in @("python", "python3")) {
        $cmds = @(Get-Command $name -All -ErrorAction SilentlyContinue)
        foreach ($cmd in $cmds) {
            if ($cmd.CommandType -ne "Application") { continue }
            if ($cmd.Source -notlike "*\WindowsApps\*") {
                $candidates += @{ Exe = $cmd.Source; Args = @() }
            }
        }
    }

    $searchRoots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe"),
        (Join-Path $env:ProgramFiles "Python3*\python.exe"),
        "C:\Python3*\python.exe"
    )
    foreach ($pattern in $searchRoots) {
        $found = @(Get-Item $pattern -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
        foreach ($item in $found) {
            $candidates += @{ Exe = $item.FullName; Args = @() }
        }
    }

    foreach ($name in @("python", "python3")) {
        $cmds = @(Get-Command $name -All -ErrorAction SilentlyContinue)
        foreach ($cmd in $cmds) {
            if ($cmd.CommandType -ne "Application") { continue }
            if ($cmd.Source -like "*\WindowsApps\*") {
                $candidates += @{ Exe = $cmd.Source; Args = @() }
            }
        }
    }

    $seen = @{}
    foreach ($cand in $candidates) {
        $key = "$($cand.Exe)|$($cand.Args -join ' ')"
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true

        $probeArgs = @($cand.Args) + @("-c", "import sys; print(1 if sys.version_info >= (3, 10) else 0)")
        $res = Invoke-NativeQuiet -Exe $cand.Exe -ArgList $probeArgs
        if ($res.ExitCode -eq 0 -and $res.Output -eq "1") {
            return $cand
        }
    }
    return $null
}

function Copy-UpdateTree {
    param(
        [string]$SourceDir,
        [string]$TargetDir
    )
    $skipRootDirs = @("data")
    $skipBackendItems = @(".env", ".venv", "cookies.txt", "downloads")

    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    }

    foreach ($item in Get-ChildItem -Path $SourceDir -Force) {
        if ($skipRootDirs -contains $item.Name) {
            continue
        }
        $destPath = Join-Path $TargetDir $item.Name
        if ($item.PSIsContainer) {
            if ($item.Name -eq "backend") {
                if (-not (Test-Path $destPath)) {
                    New-Item -ItemType Directory -Path $destPath -Force | Out-Null
                }
                foreach ($bItem in Get-ChildItem -Path $item.FullName -Force) {
                    if ($skipBackendItems -contains $bItem.Name) {
                        continue
                    }
                    $bDest = Join-Path $destPath $bItem.Name
                    if ($bItem.PSIsContainer) {
                        if (Test-Path $bDest) {
                            Copy-Item -Path (Join-Path $bItem.FullName "*") -Destination $bDest -Recurse -Force
                        } else {
                            Copy-Item -Path $bItem.FullName -Destination $bDest -Recurse -Force
                        }
                    } else {
                        Copy-Item -Path $bItem.FullName -Destination $bDest -Force
                    }
                }
            } elseif ($item.Name -eq "frontend") {
                if (-not (Test-Path $destPath)) {
                    New-Item -ItemType Directory -Path $destPath -Force | Out-Null
                }
                foreach ($fItem in Get-ChildItem -Path $item.FullName -Force) {
                    if ($fItem.Name -eq "node_modules" -or $fItem.Name -eq ".next") {
                        continue
                    }
                    $fDest = Join-Path $destPath $fItem.Name
                    if ($fItem.Name -eq "out" -and (Test-Path $fDest)) {
                        Remove-Item -Path $fDest -Recurse -Force
                    }
                    if ($fItem.PSIsContainer) {
                        if (Test-Path $fDest) {
                            Copy-Item -Path (Join-Path $fItem.FullName "*") -Destination $fDest -Recurse -Force
                        } else {
                            Copy-Item -Path $fItem.FullName -Destination $fDest -Recurse -Force
                        }
                    } else {
                        Copy-Item -Path $fItem.FullName -Destination $fDest -Force
                    }
                }
            } else {
                if (Test-Path $destPath) {
                    Copy-Item -Path (Join-Path $item.FullName "*") -Destination $destPath -Recurse -Force
                } else {
                    Copy-Item -Path $item.FullName -Destination $destPath -Recurse -Force
                }
            }
        } else {
            Copy-Item -Path $item.FullName -Destination $destPath -Force
        }
    }
}

Write-Host "=== YT-Sum Knowledge Navigator Installer (Windows) ===" -ForegroundColor Cyan
Write-Host "Install directory: $InstallDir" -ForegroundColor Gray

# Step 1: Check Python 3.10+
Write-Host "`n[1/5] Checking Python 3.10+..." -ForegroundColor Cyan
$py = Find-Python310
if (-not $py) {
    $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetCmd -and (Test-IsInteractive)) {
        if (Read-YesNo "Python 3.10+ was not found. Install Python 3.12 automatically via winget? [Y/n]" $true) {
            Write-Host "Installing Python 3.12 via winget..." -ForegroundColor Yellow
            Invoke-NativeChecked -Exe "winget" -ArgList @(
                "install", "-e", "--id", "Python.Python.3.12",
                "--scope", "user",
                "--accept-source-agreements", "--accept-package-agreements"
            ) -ErrorMessage "winget failed to install Python 3.12."
            Refresh-ProcessPath
            $py = Find-Python310
        }
    }
}

if (-not $py) {
    Write-Host "[Error] Python 3.10 or newer is required." -ForegroundColor Red
    Write-Host "Please install Python first using one of these methods:" -ForegroundColor Yellow
    Write-Host "  1. Run in PowerShell: winget install -e --id Python.Python.3.12"
    Write-Host "  2. Download from: https://www.python.org/downloads/ (Check 'Add python.exe to PATH')"
    exit 1
}

$pyVer = Invoke-NativeQuiet -Exe $py.Exe -ArgList (@($py.Args) + @("-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')"))
Write-Host "Found Python $($pyVer.Output) ($($py.Exe))" -ForegroundColor Green

# Step 2: Download or update YT-Sum
Write-Host "`n[2/5] Downloading / updating YT-Sum..." -ForegroundColor Cyan
$hasGit = ($env:YTSUM_FORCE_ZIP -ne "1") -and [bool](Get-Command git -ErrorAction SilentlyContinue)
$gitDir = Join-Path $InstallDir ".git"

if ($hasGit -and (Test-Path $gitDir)) {
    Write-Host "Existing Git installation found. Updating via git pull --ff-only..." -ForegroundColor Gray
    Invoke-NativeChecked -Exe "git" -ArgList @("-C", $InstallDir, "pull", "--ff-only") -ErrorMessage "git pull failed. Your data/ and backend/.env were not modified. Check local changes or re-run with `$env:YTSUM_FORCE_ZIP='1'."
} elseif ($hasGit -and (-not (Test-Path $InstallDir))) {
    $parentDir = Split-Path -Parent $InstallDir
    if ($parentDir -and (-not (Test-Path $parentDir))) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    Write-Host "Cloning repository into $InstallDir..." -ForegroundColor Gray
    Invoke-NativeChecked -Exe "git" -ArgList @("clone", "--depth", "1", $RepoUrl, $InstallDir) -ErrorMessage "git clone failed."
} else {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("ytsum-install-" + [System.Guid]::NewGuid().ToString("N"))
    $zipFile = Join-Path $tempRoot "yt-sum.zip"
    $extractDir = Join-Path $tempRoot "extract"
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
    try {
        Write-Host "Downloading latest archive from GitHub..." -ForegroundColor Gray
        Invoke-WebRequest -Uri $ZipUrl -OutFile $zipFile -UseBasicParsing
        Expand-Archive -Path $zipFile -DestinationPath $extractDir -Force

        $sourceRoot = Join-Path $extractDir "yt-sum-main"
        if (-not (Test-Path (Join-Path $sourceRoot "backend\main.py"))) {
            $candidate = Get-ChildItem -Path $extractDir -Directory | Where-Object {
                Test-Path (Join-Path $_.FullName "backend\main.py")
            } | Select-Object -First 1
            if (-not $candidate) {
                throw "Extracted archive does not contain backend\main.py."
            }
            $sourceRoot = $candidate.FullName
        }

        Copy-UpdateTree -SourceDir $sourceRoot -TargetDir $InstallDir
        Write-Host "Files synced to $InstallDir (existing .env, .venv, and data/ preserved)." -ForegroundColor Green
    } finally {
        if (Test-Path $tempRoot) {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# Step 3: Set up Python venv and dependencies
Write-Host "`n[3/5] Setting up Python virtual environment and dependencies..." -ForegroundColor Cyan
$BackendDir = Join-Path $InstallDir "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Invoke-NativeChecked -Exe $py.Exe -ArgList (@($py.Args) + @("-m", "venv", $VenvDir)) -ErrorMessage "Failed to create Python virtual environment."
}

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment Python not found at $VenvPython"
}

Invoke-NativeChecked -Exe $VenvPython -ArgList @(
    "-m", "pip", "install", "--disable-pip-version-check",
    "-r", (Join-Path $BackendDir "requirements.txt")
) -ErrorMessage "Failed to install Python dependencies."

$EnvFile = Join-Path $BackendDir ".env"
$EnvExample = Join-Path $BackendDir ".env.example"
if ((-not (Test-Path $EnvFile)) -and (Test-Path $EnvExample)) {
    Copy-Item -Path $EnvExample -Destination $EnvFile -Force
}

# Step 4: Check optional FFmpeg
Write-Host "`n[4/5] Checking optional FFmpeg component..." -ForegroundColor Cyan
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "[OK] FFmpeg detected. MP3 and 1080p+ MP4 downloads are ready." -ForegroundColor Green
} else {
    Write-Host "[Info] FFmpeg not found (optional). Core AI analysis works without it." -ForegroundColor Yellow
    Write-Host "       To download MP3 or 1080p+ MP4 later, run: winget install Gyan.FFmpeg" -ForegroundColor Gray
}

# Step 5: Startup & optional background auto-start
Write-Host "`n[5/5] Configuring startup..." -ForegroundColor Cyan
$autostartChoice = Resolve-OptionalBool $env:YTSUM_AUTOSTART
if ($null -eq $autostartChoice) {
    $autostartChoice = Read-YesNo "Enable silent background auto-start on Windows login? (Recommended for desktop PWA) [Y/n]" $true
}

if ($autostartChoice) {
    $stoppedOld = $false
    $procs = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        $cmdLine = $p.CommandLine
        if ($cmdLine -and ($cmdLine.IndexOf($BackendDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -and $cmdLine.Contains("uvicorn")) {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            $stoppedOld = $true
        }
    }
    if ($stoppedOld) {
        Start-Sleep -Milliseconds 800
    }

    & (Join-Path $InstallDir "install_autostart.ps1")
    if ($env:YTSUM_NO_OPEN -ne "1") {
        Start-Process "http://localhost:8000"
    }
} else {
    Write-Host "Skipped background auto-start. You can launch anytime by double-clicking:" -ForegroundColor Gray
    Write-Host "  $(Join-Path $InstallDir 'run_app.bat')" -ForegroundColor White
    if ($env:YTSUM_NO_OPEN -ne "1") {
        if (Read-YesNo "Launch YT-Sum now? [Y/n]" $true) {
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$(Join-Path $InstallDir 'run_app.bat')`"" -WorkingDirectory $InstallDir
        }
    }
}

# Step 6: Summary
Write-Host "`n=== Installation Complete ===" -ForegroundColor Green
Write-Host "Install location : $InstallDir"
Write-Host "App URL          : http://localhost:8000"
Write-Host ""
Write-Host "First-time setup (30 seconds):" -ForegroundColor Cyan
Write-Host "  1. Click the 'Key' button at the top-right to paste your Gemini API Key"
Write-Host "     (Get a free key at https://aistudio.google.com/)"
Write-Host "  2. Click 'Install App' at the top-right to install as a Desktop PWA"
Write-Host ""
Write-Host "To update YT-Sum in the future (preserves your notes & API Key), run:" -ForegroundColor Gray
Write-Host "  irm https://raw.githubusercontent.com/Lin-Yu-kuan/yt-sum/main/install.ps1 | iex" -ForegroundColor White
