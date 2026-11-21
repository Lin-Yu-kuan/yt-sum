#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/com.ytsum.server.plist"
LOG_DIR="$HOME/Library/Logs"
LOG_PATH="$LOG_DIR/yt-sum.log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

echo "=== YT-Sum macOS 背景常駐服務安裝 ==="

if [ ! -d "$BACKEND_DIR" ]; then
    echo "[錯誤] 找不到 backend 資料夾，請確認檔案結構完整。"
    read -r -p "按 Enter 鍵關閉..."
    exit 1
fi

cd "$BACKEND_DIR"

PYTHON_BIN=""
for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
            PYTHON_BIN="$(command -v "$candidate")"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "[錯誤] 找不到 Python 3.10 以上版本，請先安裝：brew install python"
    read -r -p "按 Enter 鍵關閉..."
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/3] 首次設定：建立虛擬環境並安裝必要套件..."
    "$PYTHON_BIN" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
else
    echo "[1/3] Python 虛擬環境已就緒。"
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
fi

mkdir -p "$PLIST_DIR" "$LOG_DIR"

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$PLIST_PATH" >/dev/null 2>&1 || true

if command -v lsof >/dev/null 2>&1 && lsof -ti tcp:8000 >/dev/null 2>&1; then
    echo "[提示] 偵測到 Port 8000 已有舊服務在執行（例如之前手動開啟的 run_app.command）。"
    echo "       若後續背景常駐未更新，請先關閉該終端機視窗以免發生 Port 衝突。"
fi

echo "[2/3] 建立 LaunchAgent 背景服務 ($PLIST_PATH)..."
YT_BACKEND_DIR="$BACKEND_DIR" YT_LOG_PATH="$LOG_PATH" YT_PLIST_PATH="$PLIST_PATH" \
    "$BACKEND_DIR/.venv/bin/python" -c '
import os, plistlib
from pathlib import Path

backend_dir = os.environ["YT_BACKEND_DIR"]
log_path = os.environ["YT_LOG_PATH"]
plist_path = Path(os.environ["YT_PLIST_PATH"])

data = {
    "Label": "com.ytsum.server",
    "ProgramArguments": [
        f"{backend_dir}/.venv/bin/python",
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--no-use-colors",
    ],
    "WorkingDirectory": backend_dir,
    "EnvironmentVariables": {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    },
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": log_path,
    "StandardErrorPath": log_path,
}

with plist_path.open("wb") as fp:
    plistlib.dump(data, fp)
'

echo "[3/3] 註冊並啟動背景服務..."
launchctl enable "gui/$UID_NUM/com.ytsum.server" >/dev/null 2>&1 || true
if ! launchctl bootstrap "gui/$UID_NUM" "$PLIST_PATH" >/dev/null 2>&1; then
    launchctl unload -w "$PLIST_PATH" >/dev/null 2>&1 || true
    launchctl load -w "$PLIST_PATH"
fi
launchctl kickstart -k "gui/$UID_NUM/com.ytsum.server" >/dev/null 2>&1 || true

IS_UP=0
for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
        IS_UP=1
        break
    fi
    sleep 0.5
done

if [ "$IS_UP" -eq 1 ]; then
    sleep 1
    if ! curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
        IS_UP=0
    fi
fi

if [ "$IS_UP" -eq 1 ]; then
    echo ""
    echo "[完成] YT-Sum 後端已在背景常駐啟動，且登入 Mac 時會自動開啟！"
    echo "現在你可以直接從 Dock / 桌面打開 YT-Sum PWA 使用。"
    open "http://localhost:8000" >/dev/null 2>&1 || true
else
    echo ""
    echo "[提示] LaunchAgent 已安裝，但尚未確認服務就緒，請檢視紀錄：$LOG_PATH"
fi

read -r -p "按 Enter 鍵關閉..."
