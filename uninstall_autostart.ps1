$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$StartupDir = [Environment]::GetFolderPath("Startup")
$VbsPath = Join-Path $StartupDir "YT-Sum-Server.vbs"

Write-Host "=== YT-Sum Windows 移除背景常駐服務 ===" -ForegroundColor Cyan

if (Test-Path $VbsPath) {
    Remove-Item $VbsPath -Force
    Write-Host "[1/2] 已移除開機自動啟動檔：$VbsPath" -ForegroundColor Green
} else {
    Write-Host "[1/2] 未發現開機自動啟動檔，略過。" -ForegroundColor Gray
}

Write-Host "[2/2] 檢查並停止背景運行中的 YT-Sum 服務..." -ForegroundColor Cyan
$StoppedCount = 0
$Procs = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue
foreach ($p in $Procs) {
    $cmd = $p.CommandLine
    if ($cmd -and $cmd.Contains($BackendDir) -and $cmd.Contains("uvicorn")) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $StoppedCount++
    }
}

if ($StoppedCount -gt 0) {
    Write-Host "已停止 $StoppedCount 個背景服務行程。" -ForegroundColor Green
} else {
    Write-Host "目前沒有執行中的 YT-Sum 背景服務。" -ForegroundColor Gray
}

Write-Host "`n移除完成！之後若要使用 YT-Sum，請手動執行 run_app.bat。" -ForegroundColor Green
