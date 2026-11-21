$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$StartupDir = [Environment]::GetFolderPath("Startup")
$VbsPath = Join-Path $StartupDir "YT-Sum-Server.vbs"

Write-Host "=== YT-Sum Windows 無黑框背景常駐安裝 ===" -ForegroundColor Cyan

if (-not (Test-Path $PythonExe)) {
    Write-Host "[1/3] 初始化 Python 虛擬環境..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "找不到 Python，請先安裝 Python 3.10+ 後重試。"
        }
    } finally {
        Pop-Location
    }
    & $PythonExe -m pip install -r (Join-Path $BackendDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Python 套件安裝失敗。"
    }
} else {
    Write-Host "[1/3] Python 虛擬環境已就緒。" -ForegroundColor Cyan
}

if (-not (Test-Path $PythonExe)) {
    throw "找不到 $PythonExe，請確認 Python 虛擬環境正常。"
}

$EnvFile = Join-Path $BackendDir ".env"
$EnvExample = Join-Path $BackendDir ".env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile -Force
}

Write-Host "[2/3] 建立開機背景自動啟動腳本 ($VbsPath)..." -ForegroundColor Cyan
$BackendEscaped = $BackendDir.Replace('"', '""')
$PythonEscaped = $PythonExe.Replace('"', '""')
$VbsContent = @"
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "$BackendEscaped"
shell.Run """$PythonEscaped"" -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-use-colors", 0, False
"@
[System.IO.File]::WriteAllText($VbsPath, $VbsContent, [System.Text.Encoding]::Unicode)

Write-Host "[3/3] 檢查並背景啟動後端服務..." -ForegroundColor Cyan
$IsUp = $false
try {
    $res = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
    if ($res.StatusCode -eq 200) { $IsUp = $true }
} catch {
    $IsUp = $false
}

if (-not $IsUp) {
    $startedDetached = $false
    try {
        $cimRes = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = "wscript.exe `"$VbsPath`""
        }
        if ($cimRes.ReturnValue -eq 0) {
            $startedDetached = $true
        }
    } catch {
        $startedDetached = $false
    }
    if (-not $startedDetached) {
        Start-Process -FilePath "wscript.exe" -ArgumentList "`"$VbsPath`""
    }
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $res = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
            if ($res.StatusCode -eq 200) {
                $IsUp = $true
                break
            }
        } catch {
            # waiting for startup
        }
    }
    if ($IsUp) {
        Start-Sleep -Seconds 1
        try {
            $confirm = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 2
            $IsUp = ($confirm.StatusCode -eq 200)
        } catch {
            $IsUp = $false
        }
    }
}

if ($IsUp) {
    Write-Host "`n[完成] YT-Sum 後端已在背景無聲啟動，並設定開機自動啟動！" -ForegroundColor Green
    Write-Host "現在你可以直接點桌面的 YT-Sum PWA 圖示使用，無需再開黑色終端機視窗。" -ForegroundColor Green
} else {
    Write-Host "`n[錯誤] 背景服務未能維持啟動，請檢查 Python 環境或執行 run_app.bat 檢視錯誤訊息。" -ForegroundColor Red
    exit 1
}
