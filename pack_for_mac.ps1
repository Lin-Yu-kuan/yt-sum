param(
    [switch]$IncludeEnv,
    [switch]$ExcludeEnv
)

$ErrorActionPreference = "Stop"

if ($IncludeEnv -and $ExcludeEnv) {
    throw "不可同時指定 -IncludeEnv 與 -ExcludeEnv。"
}

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendOut = Join-Path $RootDir "frontend\out"
$FrontendIndex = Join-Path $FrontendOut "index.html"
$BackendDir = Join-Path $RootDir "backend"
$EnvFile = Join-Path $BackendDir ".env"
$ZipPath = Join-Path $RootDir "YT-Sum-macOS-portable.zip"

Write-Host "=== YT-Sum macOS 可攜版打包工具 ===" -ForegroundColor Cyan

if (-not (Test-Path $FrontendIndex)) {
    Write-Host "[錯誤] 找不到 frontend\out\index.html，請先執行前端編譯：" -ForegroundColor Red
    Write-Host "       cd frontend; npm run build" -ForegroundColor Yellow
    exit 1
}

$PackEnv = $false
if ($IncludeEnv) {
    $PackEnv = $true
} elseif ($ExcludeEnv) {
    $PackEnv = $false
} elseif (Test-Path $EnvFile) {
    $ans = Read-Host "是否連同本機 backend\.env（含共用 Gemini API Key）一併打包給朋友？(y/N)"
    if ($ans -match "^(y|yes)$") {
        $PackEnv = $true
    }
}

if ($PackEnv -and -not (Test-Path $EnvFile)) {
    Write-Host "[警告] 指定了 -IncludeEnv，但找不到 backend\.env，將略過 .env。" -ForegroundColor Yellow
    $PackEnv = $false
}

$StagingDir = Join-Path ([System.IO.Path]::GetTempPath()) ("yt-sum-pack-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

function Copy-FilteredDirectory {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeNames
    )
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($item in Get-ChildItem -Path $Source -Force) {
        if ($ExcludeNames -contains $item.Name) {
            continue
        }
        $target = Join-Path $Destination $item.Name
        if ($item.PSIsContainer) {
            Copy-FilteredDirectory -Source $item.FullName -Destination $target -ExcludeNames $ExcludeNames
        } else {
            if ($item.Extension -in ".pyc", ".pyo") { continue }
            Copy-Item -Path $item.FullName -Destination $target -Force
        }
    }
}

try {
    Write-Host "[1/3] 複製 backend（排除 .venv、快取與個人暫存檔）..." -ForegroundColor Cyan
    $BackendStage = Join-Path $StagingDir "backend"
    $ExcludeBackend = @(".venv", "__pycache__", ".pytest_cache", "cookies.txt", "downloads", ".env")
    Copy-FilteredDirectory -Source $BackendDir -Destination $BackendStage -ExcludeNames $ExcludeBackend

    if ($PackEnv) {
        Copy-Item -Path $EnvFile -Destination (Join-Path $BackendStage ".env") -Force
        Write-Host "      已帶入共用 backend\.env（請務必私下傳送此壓縮檔）。" -ForegroundColor Yellow
    }

    Write-Host "[2/3] 複製 frontend\out 與啟動腳本..." -ForegroundColor Cyan
    $FrontendOutStage = Join-Path $StagingDir "frontend\out"
    Copy-FilteredDirectory -Source $FrontendOut -Destination $FrontendOutStage -ExcludeNames @(".DS_Store")

    foreach ($rootFile in @("run_app.command", "run_app.bat", "README.md")) {
        $srcFile = Join-Path $RootDir $rootFile
        if (Test-Path $srcFile) {
            Copy-Item -Path $srcFile -Destination (Join-Path $StagingDir $rootFile) -Force
        }
    }

    # 確保打包進去的 run_app.command 為純 LF 換行
    $cmdStage = Join-Path $StagingDir "run_app.command"
    if (Test-Path $cmdStage) {
        $raw = [System.IO.File]::ReadAllText($cmdStage, [System.Text.UTF8Encoding]::new($false))
        $lf = $raw.Replace("`r`n", "`n")
        [System.IO.File]::WriteAllText($cmdStage, $lf, [System.Text.UTF8Encoding]::new($false))
    }

    Write-Host "[3/3] 壓縮產出 $ZipPath ..." -ForegroundColor Cyan
    if (Test-Path $ZipPath) {
        Remove-Item $ZipPath -Force
    }
    Compress-Archive -Path (Join-Path $StagingDir "*") -DestinationPath $ZipPath -Force

    $zipInfo = Get-Item $ZipPath
    $sizeMb = [Math]::Round($zipInfo.Length / 1MB, 2)
    Write-Host "`n打包完成：$ZipPath ($sizeMb MB)" -ForegroundColor Green
    if ($PackEnv) {
        Write-Host "[安全提醒] 此壓縮檔包含你的 Gemini API Key (backend\.env)，請勿上傳至公開網路或 Git！" -ForegroundColor Yellow
    } else {
        Write-Host "[提示] 未打包 .env，朋友首次開啟後可直接在網頁右上角 Key 按鈕輸入 API Key。" -ForegroundColor Gray
    }
} finally {
    if (Test-Path $StagingDir) {
        Remove-Item $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
